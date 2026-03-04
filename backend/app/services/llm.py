from langchain_core.prompts import PromptTemplate
from typing import List
import re
import json
from config import model, parser


# ---- Chains ----

_questions_chain = (
    PromptTemplate(
        input_variables=["profile_text", "posts_blob"],
        template=(
            "You are an expert interview designer.\n"
            "Generate exactly 5 high-intelligence behavioral interview questions using ONLY the candidate evidence below.\n"
            "Rules:\n"
            "1) No generic templates and no repeated structure.\n"
            "2) Every question must reference at least one concrete profile signal (role/company/skill/location/education/cert/focus).\n"
            "3) Questions must probe decision quality, tradeoff logic, ownership, and thought process.\n"
            "4) Keep each question under 35 words.\n"
            '5) Return strict JSON with shape: {{"questions":["...","...","...","...","..."]}}\n\n'
            "Candidate Evidence:\n{profile_text}\n\n"
            "Recent Posts:\n{posts_blob}\n"
        ),
    )
    | model
    | parser
)

_topics_chain = (
    PromptTemplate(
        input_variables=["profile_text", "posts_blob", "answers_blob"],
        template=(
            "Extract 5-8 concise professional interest topics from LinkedIn profile data, posts, and answers. "
            "Return comma-separated topics with no extra text.\n\n"
            "LinkedIn Profile Snapshot:\n{profile_text}\n\n"
            "Recent Posts:\n{posts_blob}\n\n"
            "Answers:\n{answers_blob}\n"
        ),
    )
    | model
    | parser
)

_reasoning_chain = (
    PromptTemplate(
        input_variables=["profile_text", "posts_blob", "answers_blob"],
        template=(
            "Write a single, concise sentence that explains the strongest shared themes across "
            "the LinkedIn profile, posts, and answers. No quotes.\n\n"
            "LinkedIn Profile Snapshot:\n{profile_text}\n\n"
            "Recent Posts:\n{posts_blob}\n\n"
            "Answers:\n{answers_blob}\n"
        ),
    )
    | model
    | parser
)

_match_reasons_chain = (
    PromptTemplate(
        input_variables=["user_name", "user_brief", "matches_blob"],
        template=(
            "You are given a LinkedIn user and a list of matched professionals.\n"
            "For EACH match, write ONE short sentence (max 25 words) explaining WHY they are a good match for the user.\n"
            "Focus on shared skills, industries, roles, or complementary expertise.\n"
            "Return strict JSON: {{\"reasons\":[\"...\",\"...\",\"...\"]}}\n\n"
            "User: {user_name}\n{user_brief}\n\n"
            "Matched Professionals:\n{matches_blob}\n"
        ),
    )
    | model
    | parser
)


# ---- Helpers ----

def _normalize_questions(text: str) -> List[str]:
    questions: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\d+[\).\-\s]+", "", line).strip()
        line = line.lstrip("-* ").strip()
        if line and line.endswith("?"):
            questions.append(line)
        elif line:
            questions.append(line + "?")

    deduped: List[str] = []
    seen = set()
    for q in questions:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(q)
    return deduped


# ---- Public API ----

def generate_questions(profile_text: str, recent_posts: List[str]) -> List[str]:
    posts_blob = "\n".join([f"- {p}" for p in recent_posts])
    try:
        text = _questions_chain.invoke({"profile_text": profile_text, "posts_blob": posts_blob})
        questions: List[str] = []
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                payload = json.loads(json_match.group(0))
                raw_questions = payload.get("questions", [])
                if isinstance(raw_questions, list):
                    questions = [str(q).strip() for q in raw_questions if str(q).strip()]
            except Exception:
                questions = []
        if not questions:
            questions = _normalize_questions(text)
        return questions[:5] if questions else []
    except Exception:
        return []


def extract_topics(profile_text: str, recent_posts: List[str], answers_blob: str) -> List[str]:
    posts_blob = "\n".join([f"- {p}" for p in recent_posts])
    try:
        text = _topics_chain.invoke({"profile_text": profile_text, "posts_blob": posts_blob, "answers_blob": answers_blob})
        topics = [t.strip() for t in text.split(",") if t.strip()]
        return topics[:8]
    except Exception:
        return []


def generate_reasoning(profile_text: str, recent_posts: List[str], answers_blob: str) -> str:
    posts_blob = "\n".join([f"- {p}" for p in recent_posts])
    try:
        return _reasoning_chain.invoke({"profile_text": profile_text, "posts_blob": posts_blob, "answers_blob": answers_blob}).strip()
    except Exception:
        return ""


def generate_match_reasons(
    user_name: str,
    user_brief: str,
    match_names: List[str],
    match_headlines: List[str],
) -> List[str]:
    matches_blob = "\n".join(
        [f"{i+1}. {n} — {h}" for i, (n, h) in enumerate(zip(match_names, match_headlines))]
    )
    try:
        text = _match_reasons_chain.invoke({
            "user_name": user_name,
            "user_brief": user_brief,
            "matches_blob": matches_blob,
        })
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            payload = json.loads(json_match.group(0))
            reasons = payload.get("reasons", [])
            if isinstance(reasons, list):
                return [str(r).strip() for r in reasons]
        return []
    except Exception:
        return []
