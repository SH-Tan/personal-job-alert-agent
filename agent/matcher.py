import json
from typing import Any
import os
import requests

INTERNSHIP_TERMS = (
    "intern",
    "internship",
    "student",
    "university",
    "campus",
    "new grad intern",
)

NEGATIVE_TERMS = (
    "senior ",
    "staff ",
    "principal ",
    "manager",
    "director",
    "sales",
    "account executive",
    "full-time only",
)


def _llm_match(provider: str, model: str, prompt: str) -> dict[str, Any]:
    provider = provider.lower()

    if provider == "gemini":
        api_key = os.environ["GEMINI_API_KEY"]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )

        gemini_payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": "Return valid JSON only.\n\n" + prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        }

        r = requests.post(url, json=gemini_payload, timeout=60)
        r.raise_for_status()
        content = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _loads_match(content)

    if provider in {"groq", "openrouter"}:
        if provider == "groq":
            api_key = os.environ["GROQ_API_KEY"]
            url = "https://api.groq.com/openai/v1/chat/completions"
        else:
            api_key = os.environ["OPENROUTER_API_KEY"]
            url = "https://openrouter.ai/api/v1/chat/completions"

        chat_payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=chat_payload,
            timeout=60,
        )
        r.raise_for_status()

        content = r.json()["choices"][0]["message"]["content"]
        return _loads_match(content)

    raise ValueError(f"Unsupported provider: {provider}")


def _loads_match(content: str | None) -> dict[str, Any]:
    if not content:
        raise ValueError("LLM response did not include JSON content.")

    parsed = json.loads(content)

    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON was not an object.")

    return parsed


def _choose_search_profile(job_text: str, search_profiles: list[dict]) -> tuple[str, str, int]:
    best_name = ""
    best_cv = ""
    best_score = 0

    for profile in search_profiles:
        keywords = [x.lower() for x in profile.get("keywords", [])]
        target_jobs = [x.lower() for x in profile.get("target_jobs", [])]
        hits = sum(1 for keyword in keywords if keyword in job_text)
        hits += 2 * sum(1 for title in target_jobs if title in job_text)

        if hits > best_score:
            best_name = profile.get("name", "")
            best_cv = profile.get("cv", "")
            best_score = hits

    return best_name, best_cv, best_score


def _heuristic_match(job: dict, search_profiles: list[dict]) -> dict[str, Any]:
    text = " ".join(
        [
            str(job.get("title", "")),
            str(job.get("company", "")),
            str(job.get("description", "")),
        ]
    ).lower()
    search_profile_name, matched_cv, profile_hits = _choose_search_profile(text, search_profiles)
    internship_hit = any(term in text for term in INTERNSHIP_TERMS)
    negative_hits = [term.strip() for term in NEGATIVE_TERMS if term in text]
    positive_signals = []

    for signal in (
        "machine learning",
        "ai research",
        "software engineering",
        "backend",
        "infrastructure",
        "robotics",
        "autonomy",
        "autonomous",
        "python",
        "pytorch",
    ):
        if signal in text:
            positive_signals.append(signal)

    score = 45

    if internship_hit:
        score += 20

    score += min(profile_hits * 7, 25)
    score += min(len(positive_signals) * 3, 15)
    score -= min(len(negative_hits) * 12, 30)
    score = max(0, min(score, 100))

    if score >= 90:
        action = "apply_immediately"
    elif score >= 75:
        action = "apply_soon"
    elif score >= 60:
        action = "save"
    else:
        action = "ignore"

    return {
        "score": score,
        "matched_cv": matched_cv,
        "search_profile": search_profile_name,
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "is_internship": internship_hit,
        "is_research_related": any(
            term in text for term in ("research", "machine learning", "ai", "robotics")
        ),
        "is_application_open": True,
        "reason": "Local keyword scoring was used to reduce LLM API usage.",
        "positive_signals": positive_signals,
        "negative_signals": negative_hits,
        "recommended_action": action,
    }


def _quick_match(job: dict, search_profiles: list[dict]) -> dict | None:
    text = " ".join(
        [
            str(job.get("title", "")),
            str(job.get("company", "")),
            str(job.get("description", "")),
        ]
    ).lower()

    internship_hit = any(term in text for term in INTERNSHIP_TERMS)
    negative_hits = [term.strip() for term in NEGATIVE_TERMS if term in text]
    search_profile_name, matched_cv, profile_hits = _choose_search_profile(text, search_profiles)

    if not internship_hit:
        return {
            "score": 10,
            "matched_cv": matched_cv,
            "search_profile": search_profile_name,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "is_internship": False,
            "is_research_related": False,
            "is_application_open": True,
            "reason": "No internship or student-specific signal was found in the title or description.",
            "positive_signals": [],
            "negative_signals": ["No internship indication"],
            "recommended_action": "ignore",
        }

    if negative_hits and profile_hits == 0:
        return {
            "score": 25,
            "matched_cv": matched_cv,
            "search_profile": search_profile_name,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "is_internship": True,
            "is_research_related": False,
            "is_application_open": True,
            "reason": "The posting contains stronger senior/full-time signals than internship-relevant role signals.",
            "positive_signals": ["Internship-related language"],
            "negative_signals": negative_hits,
            "recommended_action": "ignore",
        }

    return None


def match_job_against_profiles(
    job: dict,
    profiles: dict,
    search_profiles: list[dict],
    config: dict,
) -> dict:
    quick_result = _quick_match(job, search_profiles)

    if quick_result is not None:
        return quick_result
    
    llm_cfg = config.get("llm", {})
    
    heuristic = _heuristic_match(job, search_profiles)

    if not llm_cfg.get("use_for_matching", False):
        return heuristic

    if heuristic["score"] >= 80 or heuristic["score"] <= 40:
        return heuristic

    prompt = f"""
You are a strict internship matching system.

Given:
1. Multiple CV-derived profiles
2. Search profiles containing keywords and target jobs
3. One job/post/email

Choose the best matching CV and search profile.
Then score the opportunity.

Return JSON only:
{{
  "score": 0,
  "matched_cv": "...",
  "search_profile": "...",
  "title": "...",
  "company": "...",
  "is_internship": true,
  "is_research_related": true,
  "is_application_open": true,
  "reason": "...",
  "positive_signals": [],
  "negative_signals": [],
  "recommended_action": "ignore | save | apply_soon | apply_immediately"
}}

Scoring:
- 90-100: excellent match, notify immediately
- 75-89: good match, include in notification
- 60-74: maybe useful, save but do not notify
- <60: ignore

Strong positive signals:
- internship
- PhD internship
- machine learning
- AI research
- robotics
- autonomy
- autonomous vehicles
- AI safety
- neural network robustness
- Python / PyTorch
- research scientist intern
- software engineering intern if relevant to selected CV

Negative signals:
- full-time only
- senior-only
- sales/business-only
- unrelated role
- no internship indication

CV profiles:
{json.dumps(profiles, indent=2)}

Search profiles:
{json.dumps(search_profiles, indent=2)}

Job/post/email:
{json.dumps(job, indent=2)}
"""

    provider = llm_cfg.get("provider", "gemini")
    model = llm_cfg.get("matching_model", "gemini-2.0-flash-lite")

    return _llm_match(provider, model, prompt)
