import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

import os
import requests


def _format_llm_error(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        details = exc.response.text[:300].replace("\n", " ")
        return f"HTTP {status}: {details}"

    return str(exc)


def _extract_json_from_llm(provider: str, prompt: str, model: str) -> dict[str, Any]:
    provider = provider.lower()

    if provider == "gemini":
        api_key = os.environ["GEMINI_API_KEY"]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        gemini_payload: dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": "Return valid JSON only.\n\n" + prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        }

        r = requests.post(url, json=gemini_payload, timeout=60)
        r.raise_for_status()
        content = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _loads_json_response(content)

    if provider == "groq":
        api_key = os.environ["GROQ_API_KEY"]
        url = "https://api.groq.com/openai/v1/chat/completions"
        groq_payload: dict[str, Any] = {
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
            json=groq_payload,
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return _loads_json_response(content)

    if provider == "openrouter":
        api_key = os.environ["OPENROUTER_API_KEY"]
        url = "https://openrouter.ai/api/v1/chat/completions"
        openrouter_payload: dict[str, Any] = {
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
            json=openrouter_payload,
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return _loads_json_response(content)

    raise ValueError(f"Unsupported LLM provider: {provider}")


def pdf_to_text(path: str) -> str:
    reader = PdfReader(path)
    pages = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)

    return "\n".join(pages)


def _extract_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    text_lower = text.lower()
    return [term for term in terms if term.lower() in text_lower]


def extract_profile_locally(cv_text: str, cv_name: str, cv_description: str) -> dict[str, Any]:
    skills = (
        "Python",
        "PyTorch",
        "TensorFlow",
        "Machine Learning",
        "Deep Learning",
        "Robotics",
        "Autonomy",
        "Computer Vision",
        "NLP",
        "C++",
        "SQL",
        "AWS",
        "Docker",
        "Linux",
        "Git",
    )
    roles = (
        "Machine Learning Intern",
        "AI Research Intern",
        "Software Engineering Intern",
        "Backend Intern",
        "Robotics Intern",
        "Research Scientist Intern",
    )
    languages = ("Python", "C++", "Java", "JavaScript", "TypeScript", "SQL", "MATLAB")
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", cv_text)
    frequent_terms = sorted({word for word in words if len(word) > 4})[:30]

    return {
        "cv_name": cv_name,
        "summary": cv_description or "Candidate profile generated locally from the CV.",
        "degree_level": "",
        "research_areas": _extract_terms(
            cv_text,
            (
                "machine learning",
                "AI safety",
                "robotics",
                "autonomous vehicles",
                "computer vision",
                "natural language processing",
                "neural network robustness",
            ),
        ),
        "technical_skills": _extract_terms(cv_text, skills),
        "programming_languages": _extract_terms(cv_text, languages),
        "tools": _extract_terms(cv_text, ("Git", "Docker", "Linux", "AWS", "CUDA", "ROS")),
        "project_keywords": frequent_terms,
        "preferred_roles": list(roles),
        "strong_match_terms": _extract_terms(cv_text, skills) + list(roles),
        "weak_match_terms": ["internship", "research", "software engineering"],
        "negative_match_terms": ["senior", "manager", "sales"],
    }


def _loads_json_response(content: str | None) -> dict[str, Any]:
    if not content:
        raise ValueError("LLM response did not include JSON content.")

    parsed = json.loads(content)

    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON was not an object.")

    return parsed


def extract_profile_from_cv(
    cv_text: str,
    cv_name: str,
    cv_description: str,
    provider: str = "gemini",
    model: str = "gemini-2.0-flash-lite",
) -> dict[str, Any]:
    prompt = f"""
You are building a personal internship monitoring agent.

Extract a structured candidate profile from this CV.

CV name:
{cv_name}

CV description:
{cv_description}

Return JSON only with:
{{
  "cv_name": "...",
  "summary": "...",
  "degree_level": "...",
  "research_areas": [],
  "technical_skills": [],
  "programming_languages": [],
  "tools": [],
  "project_keywords": [],
  "preferred_roles": [],
  "strong_match_terms": [],
  "weak_match_terms": [],
  "negative_match_terms": []
}}

CV text:
{cv_text}
"""
    return _extract_json_from_llm(provider, prompt, model)


def _profile_cache_key(config: dict) -> str:
    payload = []

    for cv_name, cv_info in sorted(config.get("cvs", {}).items()):
        cv_path = Path(cv_info["path"])
        payload.append(
            {
                "cv_name": cv_name,
                "path": str(cv_path),
                "description": cv_info.get("description", ""),
                "priority": cv_info.get("priority"),
                "mtime_ns": cv_path.stat().st_mtime_ns if cv_path.exists() else None,
            }
        )

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def load_or_build_profiles(config: dict, cache_path: str = "data/profiles.json") -> dict[str, Any]:
    cache = Path(cache_path)
    cache_key = _profile_cache_key(config)
    
    llm_cfg = config.get("llm", {})
    use_llm = bool(llm_cfg.get("use_for_cv_profile", True))
    fallback_to_local = bool(llm_cfg.get("fallback_to_local", True))
    provider = llm_cfg.get("provider", "gemini")
    model = llm_cfg.get("cv_profile_model", "gemini-2.0-flash-lite")
    
    if cache.exists():
        with open(cache, "r", encoding="utf-8") as f:
            cached = json.load(f)

        if isinstance(cached, dict) and "profiles" in cached and "cache_key" in cached:
            if cached["cache_key"] == cache_key:
                return cached["profiles"]
        elif isinstance(cached, dict):
            # Backward compatibility for the previous flat cache format.
            return cached

    profiles = {}

    for cv_name, cv_info in config["cvs"].items():
        cv_text = pdf_to_text(cv_info["path"])

        if use_llm:
            try:
                profile = extract_profile_from_cv(
                    cv_text=cv_text,
                    cv_name=cv_name,
                    cv_description=cv_info.get("description", ""),
                    provider=provider,
                    model=model,
                )
            except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as e:
                if not fallback_to_local:
                    raise

                print(
                    "[WARN] CV profile LLM extraction failed; "
                    f"using local extraction instead ({_format_llm_error(e)})."
                )
                profile = extract_profile_locally(
                    cv_text=cv_text,
                    cv_name=cv_name,
                    cv_description=cv_info.get("description", ""),
                )
        else:
            profile = extract_profile_locally(
                cv_text=cv_text,
                cv_name=cv_name,
                cv_description=cv_info.get("description", ""),
            )

        profiles[cv_name] = profile

    cache.parent.mkdir(parents=True, exist_ok=True)

    with open(cache, "w", encoding="utf-8") as f:
        json.dump(
            {
                "cache_key": cache_key,
                "profiles": profiles,
            },
            f,
            indent=2,
        )

    return profiles
