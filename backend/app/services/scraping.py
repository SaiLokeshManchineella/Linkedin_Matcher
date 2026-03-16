import requests
from typing import Dict, Any, List
from urllib.parse import urlparse
from pathlib import Path
import json
import time
from config import settings


RAPIDAPI_HOST = "fresh-linkedin-profile-data.p.rapidapi.com"
CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "linkedin_profile_cache.json"


def normalize_linkedin_url(url: str) -> str:
    """Return a canonical LinkedIn URL regardless of trailing slash or www prefix.

    Both of these map to the same key:
      https://www.linkedin.com/in/majeti-nikith/
      https://www.linkedin.com/in/majeti-nikith
    """
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    # normalise scheme + lower-case host + path (strip any trailing slash again)
    netloc = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{netloc}{path}"


def _headers() -> Dict[str, str]:
    return {
        "x-rapidapi-key": settings.rapidapi_key,
        "x-rapidapi-host": RAPIDAPI_HOST,
    }


# ---- Cache ----

def _ensure_cache_dir() -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_cache() -> Dict[str, Any]:
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    _ensure_cache_dir()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=True, indent=2)


def _get_cached(key: str) -> Any:
    cache = _load_cache()
    record = cache.get(key)
    if isinstance(record, dict):
        return record.get("data")
    return None


def _set_cached(key: str, data: Any) -> None:
    cache = _load_cache()
    cache[key] = {"cached_at": int(time.time()), "data": data}
    _save_cache(cache)


# ---- Helpers ----

def _extract_linkedin_id(linkedin_url: str) -> str:
    parsed = urlparse(linkedin_url)
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] in {"in", "company"}:
        return path_parts[1]
    if path_parts:
        return path_parts[-1]
    return ""


def _normalize_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map RapidAPI enrich-lead response to app field names."""
    if not isinstance(data, dict):
        return {}

    profile: Dict[str, Any] = {}

    # identity
    profile["fullName"] = data.get("full_name") or ""
    profile["name"] = profile["fullName"]
    profile["headline"] = data.get("headline") or data.get("job_title") or ""
    profile["about"] = data.get("about") or ""
    profile["summary"] = profile["about"]
    profile["profile_image_url"] = data.get("profile_image_url") or ""
    profile["linkedin_url"] = data.get("linkedin_url") or ""

    # location / industry
    city = data.get("city") or ""
    country = data.get("country") or ""
    profile["location"] = data.get("location") or (f"{city}, {country}".strip(", ") if (city or country) else "")
    profile["industry"] = data.get("company_industry") or ""
    profile["followers"] = data.get("follower_count") or ""
    profile["connections"] = data.get("connection_count") or ""

    # experience
    raw_exp = data.get("experiences") or []
    if raw_exp:
        profile["experience"] = [
            {
                "title": e.get("title") or "",
                "company": e.get("company") or "",
                "company_name": e.get("company") or "",
                "description": e.get("description") or "",
                "duration": e.get("duration") or "",
                "location": e.get("location") or "",
                "is_current": e.get("is_current", False),
            }
            for e in raw_exp if isinstance(e, dict)
        ]
        first_exp = profile["experience"][0] if profile["experience"] else {}
        profile["company"] = first_exp.get("company", "")
        profile["title"] = first_exp.get("title", "")

    # education
    raw_edu = data.get("educations") or []
    if raw_edu:
        profile["education"] = [
            {
                "institution": ed.get("school") or "",
                "school": ed.get("school") or "",
                "degree": ed.get("degree") or "",
                "field": ed.get("field_of_study") or "",
            }
            for ed in raw_edu if isinstance(ed, dict)
        ]

    # skills
    raw_skills = data.get("skills") or []
    if isinstance(raw_skills, list) and raw_skills:
        profile["skills"] = [
            (s if isinstance(s, str) else (s.get("name") or "")) for s in raw_skills
        ]

    # certifications
    raw_certs = data.get("certifications") or []
    if raw_certs:
        profile["certification"] = [
            {"certification": c.get("name") or ""} for c in raw_certs if isinstance(c, dict)
        ]

    # urn (needed for posts search)
    if data.get("urn"):
        profile["urn"] = data["urn"]
    if data.get("public_id"):
        profile["public_id"] = data["public_id"]

    return profile


# ---- Public API ----

def fetch_linkedin_profile(linkedin_url: str) -> Dict[str, Any]:
    """Fetch a LinkedIn profile via RapidAPI fresh-linkedin-profile-data."""
    if not settings.rapidapi_key:
        return {"error": "RAPIDAPI_KEY not set"}

    profile_id = _extract_linkedin_id(linkedin_url)
    if not profile_id:
        return {"error": "Could not parse LinkedIn profile id from URL."}

    cache_key = f"profile:{profile_id}"
    cached = _get_cached(cache_key)
    if isinstance(cached, dict) and cached:
        return cached

    try:
        resp = requests.get(
            f"https://{RAPIDAPI_HOST}/enrich-lead",
            params={
                "linkedin_url": linkedin_url,
                "include_skills": "true",
                "include_certifications": "true",
            },
            headers=_headers(),
            timeout=60,
        )
        if resp.status_code >= 400:
            msg = f"RapidAPI request failed ({resp.status_code})."
            try:
                body = resp.json()
                if isinstance(body, dict):
                    msg = body.get("message") or msg
            except Exception:
                pass
            return {"error": msg}

        raw = resp.json()
        inner = raw.get("data", raw) if isinstance(raw, dict) else raw
        profile = _normalize_profile(inner)

        has_signal = any(
            profile.get(k) for k in ("fullName", "headline", "about", "experience", "education")
        )
        if not has_signal:
            return {"error": f"No profile data returned for '{profile_id}'.", "raw": raw}

        _set_cached(cache_key, profile)
        return profile
    except Exception as exc:
        return {"error": str(exc)}


def fetch_recent_posts(linkedin_url: str, urn: str, limit: int = 15) -> List[str]:
    """Fetch recent posts for a LinkedIn profile via RapidAPI search-posts."""
    if not settings.rapidapi_key or not urn:
        return []

    profile_id = _extract_linkedin_id(linkedin_url)
    cache_key = f"posts:{profile_id}"
    cached = _get_cached(cache_key)
    if isinstance(cached, list) and cached:
        return cached[:limit]

    try:
        resp = requests.post(
            f"https://{RAPIDAPI_HOST}/search-posts",
            headers={**_headers(), "Content-Type": "application/json"},
            json={
                "search_keywords": "",
                "sort_by": "",
                "date_posted": "",
                "content_type": "",
                "from_member": [urn],
                "from_company": [],
                "mentioning_member": [],
                "mentioning_company": [],
                "author_company": [],
                "author_industry": [],
                "author_keyword": "",
                "page": 1,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        items = data.get("data", []) if isinstance(data, dict) else []
        posts: List[str] = []
        for item in items:
            if isinstance(item, dict):
                text = (item.get("text") or "").strip()
                if text:
                    posts.append(text)
            if len(posts) >= limit:
                break

        if posts:
            _set_cached(cache_key, posts)
        return posts[:limit]
    except Exception:
        return []


def search_linkedin_by_keywords(keywords: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Search LinkedIn posts by keywords and extract unique poster profiles.
    Used to find similar professionals when Qdrant doesn't have enough matches.
    """
    if not settings.rapidapi_key or not keywords.strip():
        return []

    try:
        resp = requests.post(
            f"https://{RAPIDAPI_HOST}/search-posts",
            headers={**_headers(), "Content-Type": "application/json"},
            json={
                "search_keywords": keywords,
                "sort_by": "",
                "date_posted": "",
                "content_type": "",
                "from_member": [],
                "from_company": [],
                "mentioning_member": [],
                "mentioning_company": [],
                "author_company": [],
                "author_industry": [],
                "author_keyword": "",
                "page": 1,
                "author_type": "Member", # Ensure we only get people
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        items = data.get("data", []) if isinstance(data, dict) else []

        seen_urls: set = set()
        profiles: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = (item.get("poster_linkedin_url") or "").strip()
            name = (item.get("poster_name") or "").strip()
            title = (item.get("poster_title") or "").strip()
            post_text = (item.get("text") or "").strip()
            if not url or url in seen_urls or not name or "/company/" in url:
                continue
            seen_urls.add(url)
            profiles.append({
                "fullName": name,
                "name": name,
                "headline": title,
                "linkedin_url": url,
                "profile_image_url": "",
                "recent_post": post_text[:200] if post_text else "",
                "source": "linkedin_search",
            })
            if len(profiles) >= limit:
                break

        return profiles
    except Exception:
        return []
