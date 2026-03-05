from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from pathlib import Path
import hashlib
import json
import time

from config import settings
from models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    SubmitAnswersRequest,
    SubmitAnswersResponse,
    MatchedUser,
)
from services.scraping import (
    fetch_linkedin_profile,
    fetch_recent_posts,
    search_linkedin_by_keywords,
    normalize_linkedin_url,
)
from services.llm import generate_questions, extract_topics, generate_reasoning, generate_match_reasons
from services.embeddings import embed_text
from services.qdrant_store import QdrantService
from services.graph import GraphService

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

qdrant_service: QdrantService | None = None
graph_service: GraphService | None = None

TARGET_MATCHES = 10
SIMILARITY_THRESHOLD = settings.qdrant_similarity_threshold  # 0.75

RESULTS_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "user_results_cache.json"


# ---- Results-cache helpers (returning users) ----

def _load_results_cache() -> Dict[str, Any]:
    try:
        if RESULTS_CACHE_FILE.exists():
            with open(RESULTS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_user_result(
    normalized_url: str,
    full_name: str,
    result: SubmitAnswersResponse,
    topics: List[str] | None = None,
    vector: List[float] | None = None,
) -> None:
    try:
        RESULTS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cache = _load_results_cache()
        cache[normalized_url] = {
            "saved_at": int(time.time()),
            "full_name": full_name,
            "result": result.model_dump(),
            "topics": topics or [],
            "vector": vector or [],
        }
        with open(RESULTS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=True, indent=2)
    except Exception:
        pass


def _get_user_result(normalized_url: str) -> Optional[Dict[str, Any]]:
    cache = _load_results_cache()
    record = cache.get(normalized_url)
    return record if isinstance(record, dict) else None


# ---- Matching pipeline (shared by /analyze returning-user and /submit_answers) ----

def _run_matching(
    normalized_url: str,
    topics: List[str],
    vector: List[float],
    profile: dict,
    profile_brief: str,
    recent_posts: List[str],
    reasoning: str,
) -> SubmitAnswersResponse:
    """Run the 3-source matching pipeline and return fresh results."""
    assert qdrant_service is not None
    assert graph_service is not None

    has_valid_vector = len(vector) == 768
    signals = _profile_signals(profile, recent_posts)

    # Ensure user is in Qdrant
    if has_valid_vector:
        user_payload = {
            "linkedin_url": normalized_url,
            "fullName": profile.get("fullName", ""),
            "headline": profile.get("headline", ""),
            "profile_image_url": profile.get("profile_image_url", ""),
            "topics": topics,
            "about": (profile.get("about") or "")[:300],
            "company": profile.get("company", ""),
            "location": profile.get("location", ""),
        }
        qdrant_service.upsert_user(vector, user_payload)

    # Ensure user is in Neo4j graph
    graph_service.write_user_graph(
        linkedin_url=normalized_url,
        full_name=profile.get("fullName", ""),
        headline=profile.get("headline", ""),
        profile_image_url=profile.get("profile_image_url", ""),
        topics=topics,
        reasoning=reasoning,
    )

    # ---- Source 1: Qdrant vector similarity ----
    db_matches: List[Dict[str, Any]] = []
    if has_valid_vector:
        db_matches = qdrant_service.find_similar_users(
            vector,
            limit=TARGET_MATCHES,
            threshold=SIMILARITY_THRESHOLD,
            exclude_url=normalized_url,
        )

    seen_urls = {m.get("linkedin_url", "") for m in db_matches}
    seen_urls.add(normalized_url)

    # ---- Source 2: Neo4j graph (shared topics) ----
    graph_matches: List[Dict[str, Any]] = []
    remaining = TARGET_MATCHES - len(db_matches)
    if remaining > 0:
        raw_graph = graph_service.find_similar_by_topics(
            linkedin_url=normalized_url,
            limit=remaining + 5,
        )
        for gm in raw_graph:
            if gm.get("linkedin_url") in seen_urls:
                continue
            seen_urls.add(gm["linkedin_url"])
            graph_matches.append(gm)
            if len(graph_matches) >= remaining:
                break

    # ---- Source 3: LinkedIn keyword search (backfill) ----
    linkedin_matches: List[Dict[str, Any]] = []
    remaining = TARGET_MATCHES - len(db_matches) - len(graph_matches)
    if remaining > 0 and topics:
        search_keywords = ", ".join(topics[:3])
        linkedin_profiles = search_linkedin_by_keywords(search_keywords, limit=remaining + 5)

        for lp in linkedin_profiles:
            if lp.get("linkedin_url") in seen_urls:
                continue
            seen_urls.add(lp["linkedin_url"])
            lp["source"] = "linkedin_search"
            lp["similarity"] = 0.0
            lp["topics"] = topics[:3]
            linkedin_matches.append(lp)
            if len(linkedin_matches) >= remaining:
                break

    # Build final matched users list (priority: Qdrant > Graph > LinkedIn)
    all_matches = db_matches + graph_matches + linkedin_matches

    # Generate per-user match reasons using AI
    if all_matches:
        match_names = [m.get("fullName", "Unknown") for m in all_matches]
        match_headlines = [m.get("headline", "") for m in all_matches]
        reasons = generate_match_reasons(
            user_name=profile.get("fullName", ""),
            user_brief=profile_brief,
            match_names=match_names,
            match_headlines=match_headlines,
        )
    else:
        reasons = []

    matched_users: List[MatchedUser] = []
    for i, m in enumerate(all_matches[:TARGET_MATCHES]):
        reason = reasons[i] if i < len(reasons) else "Similar professional profile and interests."
        matched_users.append(MatchedUser(
            fullName=m.get("fullName", ""),
            headline=m.get("headline", ""),
            linkedin_url=m.get("linkedin_url", ""),
            profile_image_url=m.get("profile_image_url", ""),
            similarity=m.get("similarity", 0.0),
            topics=m.get("topics", topics[:3]),
            reason=reason,
            source=m.get("source", "qdrant"),
        ))

    return SubmitAnswersResponse(
        user_topics=topics,
        user_reasoning=reasoning,
        matched_users=matched_users,
        total_from_db=len(db_matches),
        total_from_graph=len(graph_matches),
        total_from_linkedin=len(linkedin_matches),
    )


# ---- Profile helpers ----

def _profile_to_text(profile: dict) -> str:
    if not isinstance(profile, dict):
        return ""
    fields = [
        "fullName", "name", "headline", "about", "summary",
        "location", "industry", "company", "title", "followers", "connections",
    ]
    chunks = []
    for key in fields:
        value = profile.get(key)
        if value:
            chunks.append(f"{key}: {value}")
    skills = profile.get("skills")
    if isinstance(skills, list) and skills:
        chunks.append("skills: " + ", ".join([str(s) for s in skills[:12]]))
    experience = profile.get("experience")
    if isinstance(experience, list) and experience:
        formatted_exp = []
        for item in experience[:5]:
            if isinstance(item, dict):
                title = item.get("title", "")
                company = item.get("company", "") or item.get("company_name", "")
                if title or company:
                    formatted_exp.append(f"{title} at {company}".strip())
        if formatted_exp:
            chunks.append("experience: " + "; ".join(formatted_exp))
    education = profile.get("education")
    if isinstance(education, list) and education:
        formatted_edu = []
        for item in education[:3]:
            if isinstance(item, dict):
                school = item.get("school", "")
                degree = item.get("degree", "")
                field = item.get("field", "")
                if school:
                    formatted_edu.append(f"{degree} {field} at {school}".strip())
        if formatted_edu:
            chunks.append("education: " + "; ".join(formatted_edu))
    return "\n".join(chunks)


def _profile_signals(profile: dict, recent_posts: List[str]) -> dict:
    name = profile.get("fullName") or profile.get("name") or "This candidate"
    about = profile.get("about") or profile.get("summary") or ""
    location = profile.get("location") or ""
    experience = profile.get("experience")
    company = ""
    role = ""
    if isinstance(experience, list) and experience:
        first = experience[0] if isinstance(experience[0], dict) else {}
        company = first.get("company_name") or first.get("company") or ""
        role = first.get("title") or ""

    skills = profile.get("skills")
    top_skill = ""
    second_skill = ""
    if isinstance(skills, list) and skills:
        top_skill = str(skills[0])
        if len(skills) > 1:
            second_skill = str(skills[1])

    education = profile.get("education")
    school = ""
    if isinstance(education, list) and education:
        edu = education[0] if isinstance(education[0], dict) else {}
        school = edu.get("institution") or edu.get("school") or ""

    certs = profile.get("certification")
    cert_name = ""
    if isinstance(certs, list) and certs:
        cert = certs[0] if isinstance(certs[0], dict) else {}
        cert_name = cert.get("certification") or ""

    focus = recent_posts[0][:110] if recent_posts else (about[:110] if about else "")
    return {
        "name": name, "about": about, "location": location,
        "company": company, "role": role,
        "top_skill": top_skill, "second_skill": second_skill,
        "school": school, "cert_name": cert_name, "focus": focus,
    }


def _profile_brief(signals: dict) -> str:
    lines = []
    for key in ["name", "about", "location", "company", "role",
                 "top_skill", "second_skill", "school", "cert_name", "focus"]:
        value = str(signals.get(key) or "").strip()
        if value:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _fallback_questions(signals: dict, recent_posts: List[str]) -> List[str]:
    name = signals.get("name") or "This candidate"
    about = signals.get("about") or "your current professional direction"
    location = signals.get("location") or "your target market"
    company = signals.get("company")
    role = signals.get("role")
    top_skill = signals.get("top_skill")
    second_skill = signals.get("second_skill")
    school = signals.get("school")
    cert_name = signals.get("cert_name")
    focus = signals.get("focus") or "the topics highlighted in your LinkedIn profile"

    pool: List[str] = []
    pool.append(f"{name}, what measurable outcome came from your recent focus on '{focus}'?")
    pool.append(f"Given your direction around '{about}', what problem do you want to own end-to-end in the next 12 months?")
    pool.append(f"In {location}, which constraint do you think most teams underestimate?")
    pool.append("Describe a decision where you changed your initial hypothesis after seeing contradictory evidence.")
    pool.append("When delivery pressure increases, what quality bar do you refuse to compromise, and why?")
    if company and role:
        pool.append(f"In your {role} scope at {company}, how do you balance immediate delivery vs long-term architecture?")
    if top_skill and second_skill:
        pool.append(f"When {top_skill} and {second_skill} priorities conflict, how do you sequence work?")
    elif top_skill:
        pool.append(f"Which problem class is best solved with {top_skill}, and what signal tells you to switch approach?")
    if school:
        pool.append(f"What principle from {school} still changes how you solve ambiguous problems today?")
    if cert_name:
        pool.append(f"From {cert_name}, what framework do you actually use in production decisions?")
    if recent_posts:
        pool.append("Pick one recent post you shared. What belief does it reveal about how you evaluate opportunities?")

    fingerprint = f"{name}|{company}|{role}|{top_skill}|{location}"
    offset = int(hashlib.md5(fingerprint.encode("utf-8")).hexdigest(), 16) % max(len(pool), 1)
    ordered = pool[offset:] + pool[:offset]
    return ordered[:5]


def _fallback_reasoning(signals: dict) -> str:
    company = signals.get("company")
    top_skill = signals.get("top_skill")
    about = signals.get("about")
    if company and top_skill:
        return f"Profile signals suggest a builder mindset centered on {top_skill} with execution exposure at {company}."
    if about:
        return f"Profile signals emphasize {about[:120]}."
    return "Questions are tuned to infer interest areas, decision frameworks, and collaboration style from LinkedIn signals."


# ---- Lifecycle ----

@app.on_event("startup")
def on_startup() -> None:
    global qdrant_service, graph_service
    qdrant_service = QdrantService()
    graph_service = GraphService()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if graph_service:
        graph_service.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---- Step 1: Analyze profile & generate questions ----

@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    normalized_url = normalize_linkedin_url(payload.linkedin_url)

    # ---- Returning-user: skip questions but re-run matching for fresh results ----
    existing = _get_user_result(normalized_url)
    if existing:
        cached_topics = existing.get("topics", [])
        cached_vector = existing.get("vector", [])

        # Re-fetch profile from cache (no API call — scraping cache handles this)
        profile = fetch_linkedin_profile(normalized_url)
        if profile.get("error"):
            profile = {}  # fallback: proceed without profile

        urn = profile.get("urn", "")
        recent_posts = fetch_recent_posts(normalized_url, urn, limit=15) if urn else []
        profile_text = _profile_to_text(profile)
        signals = _profile_signals(profile, recent_posts)
        profile_brief = _profile_brief(signals)
        reasoning = existing.get("result", {}).get("user_reasoning", "")
        if not reasoning:
            reasoning = _fallback_reasoning(signals)

        # Re-run matching with stored topics + vector for FRESH results
        if cached_topics and cached_vector:
            fresh_result = _run_matching(
                normalized_url=normalized_url,
                topics=cached_topics,
                vector=cached_vector,
                profile=profile,
                profile_brief=profile_brief,
                recent_posts=recent_posts,
                reasoning=reasoning,
            )
            # Update cache with fresh results
            _save_user_result(
                normalized_url=normalized_url,
                full_name=existing.get("full_name", ""),
                result=fresh_result,
                topics=cached_topics,
                vector=cached_vector,
            )
            return AnalyzeResponse(
                profile={},
                recent_posts=[],
                questions=[],
                reasoning="",
                returning_user=True,
                returning_full_name=existing.get("full_name", ""),
                cached_result=fresh_result.model_dump(),
            )

        # Fallback: old cache entry without topics/vector — recover them
        # Try to get topics from the cached result's user_topics field
        if not cached_topics:
            cached_topics = existing.get("result", {}).get("user_topics", [])
        # Read the ORIGINAL vector from Qdrant (has profile+answers quality)
        # instead of regenerating a degraded profile-only vector
        if not cached_vector:
            cached_vector = qdrant_service.get_user_vector(normalized_url)

        if cached_topics and cached_vector:
            fresh_result = _run_matching(
                normalized_url=normalized_url,
                topics=cached_topics,
                vector=cached_vector,
                profile=profile,
                profile_brief=profile_brief,
                recent_posts=recent_posts,
                reasoning=reasoning,
            )
            # Update cache with recovered topics + vector
            _save_user_result(
                normalized_url=normalized_url,
                full_name=existing.get("full_name", ""),
                result=fresh_result,
                topics=cached_topics,
                vector=cached_vector,
            )
            return AnalyzeResponse(
                profile={},
                recent_posts=[],
                questions=[],
                reasoning="",
                returning_user=True,
                returning_full_name=existing.get("full_name", ""),
                cached_result=fresh_result.model_dump(),
            )

        # Last resort: return whatever was in cache
        return AnalyzeResponse(
            profile={},
            recent_posts=[],
            questions=[],
            reasoning="",
            returning_user=True,
            returning_full_name=existing.get("full_name", ""),
            cached_result=existing.get("result"),
        )

    # ---- New user ----
    profile = fetch_linkedin_profile(normalized_url)
    if profile.get("error"):
        raise HTTPException(status_code=502, detail=f"LinkedIn fetch failed: {profile['error']}")

    # Fetch recent posts using URN
    urn = profile.get("urn", "")
    recent_posts = fetch_recent_posts(normalized_url, urn, limit=15) if urn else []

    profile_text = _profile_to_text(profile)
    signals = _profile_signals(profile, recent_posts)
    profile_brief = _profile_brief(signals)

    questions = generate_questions(profile_brief, recent_posts)
    if len(questions) < 5:
        questions = _fallback_questions(signals, recent_posts)

    reasoning = generate_reasoning(profile_brief, recent_posts, "")
    if not reasoning.strip():
        reasoning = _fallback_reasoning(signals)

    return AnalyzeResponse(
        profile=profile,
        recent_posts=recent_posts,
        questions=questions,
        reasoning=reasoning,
    )


# ---- Step 2: Submit answers, find similar users ----

@app.post("/submit_answers", response_model=SubmitAnswersResponse)
def submit_answers(payload: SubmitAnswersRequest) -> SubmitAnswersResponse:
    assert qdrant_service is not None
    assert graph_service is not None

    normalized_url = normalize_linkedin_url(payload.linkedin_url)
    answers_blob = "\n".join([f"Q: {a.question}\nA: {a.answer}" for a in payload.answers])

    # Re-fetch profile (from cache)
    profile = fetch_linkedin_profile(normalized_url)
    if profile.get("error"):
        raise HTTPException(status_code=502, detail=f"LinkedIn fetch failed: {profile['error']}")

    urn = profile.get("urn", "")
    recent_posts = fetch_recent_posts(normalized_url, urn, limit=15) if urn else []
    profile_text = _profile_to_text(profile)
    signals = _profile_signals(profile, recent_posts)
    profile_brief = _profile_brief(signals)

    # Extract topics for this user
    topics = extract_topics(profile_brief, recent_posts, answers_blob)
    if not topics:
        topics = [signals.get("top_skill", ""), signals.get("industry", ""), signals.get("company", "")]
        topics = [t for t in topics if t]

    # Build embedding from profile summary + answers
    embed_input = f"{profile_text}\n\n{answers_blob}"
    vector = embed_text(embed_input)

    # Generate reasoning for current user
    reasoning = generate_reasoning(profile_brief, recent_posts, answers_blob)
    if not reasoning.strip():
        reasoning = _fallback_reasoning(signals)

    # Run the full 3-source matching pipeline
    response = _run_matching(
        normalized_url=normalized_url,
        topics=topics,
        vector=vector,
        profile=profile,
        profile_brief=profile_brief,
        recent_posts=recent_posts,
        reasoning=reasoning,
    )

    # Persist result + topics + vector for returning-user re-matching
    _save_user_result(
        normalized_url=normalized_url,
        full_name=profile.get("fullName", ""),
        result=response,
        topics=topics,
        vector=vector,
    )

    return response
