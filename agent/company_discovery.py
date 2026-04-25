import json
from pathlib import Path
from typing import Any

import os
import requests


def _call_llm_json_list(provider: str, model: str, prompt: str) -> list[dict[str, Any]]:
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
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        }

        r = requests.post(url, json=gemini_payload, timeout=60)
        r.raise_for_status()
        content = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _loads_company_list(content)

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
            "temperature": 0.2,
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
        parsed = json.loads(content)

        if isinstance(parsed, list):
            return _loads_company_list(content)

        if isinstance(parsed, dict):
            for value in parsed.values():
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]

        raise ValueError("LLM response did not contain a company list.")

    raise ValueError(f"Unsupported provider: {provider}")


def _loads_company_list(content: str | None) -> list[dict[str, Any]]:
    if not content:
        raise ValueError("LLM response did not include JSON content.")

    parsed = json.loads(content)

    if not isinstance(parsed, list):
        raise ValueError("LLM response JSON was not a list.")

    return [item for item in parsed if isinstance(item, dict)]


def _normalize_company(company: dict[str, Any]) -> dict[str, str]:
    return {
        "name": str(company.get("name", "")).strip(),
        "careers_url": str(
            company.get("careers_url") or company.get("careers_url_guess") or ""
        ).strip(),
        "why_relevant": str(company.get("why_relevant", "")).strip(),
    }


def _dedupe_companies(companies: list[dict[str, Any]]) -> list[dict[str, str]]:
    deduped = []
    seen = set()

    for company in companies:
        normalized = _normalize_company(company)
        key = (normalized["name"].lower(), normalized["careers_url"].lower())

        if not key[0] or not key[1] or key in seen:
            continue

        seen.add(key)
        deduped.append(normalized)

    return deduped


def _load_cached_companies(cache_path: str) -> list[dict[str, str]]:
    cache = Path(cache_path)

    if not cache.exists():
        return []

    with open(cache, "r", encoding="utf-8") as f:
        cached = json.load(f)

    if not isinstance(cached, list):
        return []

    return _dedupe_companies([item for item in cached if isinstance(item, dict)])


def _save_cached_companies(cache_path: str, companies: list[dict[str, str]]) -> None:
    cache = Path(cache_path)
    cache.parent.mkdir(parents=True, exist_ok=True)

    with open(cache, "w", encoding="utf-8") as f:
        json.dump(companies, f, indent=2)


def discover_related_companies(config: dict, profiles: dict) -> list[dict]:
    discovery_cfg = config.get("company_discovery", {})
    llm_cfg = config.get("llm", {})
    cache_path = str(discovery_cfg.get("cache_path", "data/discovered_companies.json"))
    refresh_cache = bool(discovery_cfg.get("refresh_cache", False))

    if not discovery_cfg.get("enabled", False):
        return []

    cached_companies = _load_cached_companies(cache_path)

    if cached_companies and not refresh_cache:
        print(f"[INFO] Loaded {len(cached_companies)} discovered companies from cache.")
        return cached_companies

    if not llm_cfg.get("use_for_company_discovery", False):
        return cached_companies

    seed_keywords = discovery_cfg.get("seed_keywords", [])
    max_companies = discovery_cfg.get("max_companies_per_run", 20)

    profile_summaries = {
        name: {
            "summary": profile.get("summary"),
            "research_areas": profile.get("research_areas"),
            "technical_skills": profile.get("technical_skills"),
            "preferred_roles": profile.get("preferred_roles"),
        }
        for name, profile in profiles.items()
    }

    prompt = f"""
Suggest companies that are likely to have internships relevant to this candidate.

Focus on:
- machine learning
- AI research
- robotics
- autonomous vehicles
- AI safety
- cyber-physical systems
- software engineering internships

Return JSON only:
[
  {{
    "name": "Company name",
    "why_relevant": "...",
    "careers_url_guess": "https://..."
  }}
]

Max companies: {max_companies}

Seed keywords:
{json.dumps(seed_keywords, indent=2)}

Candidate profiles:
{json.dumps(profile_summaries, indent=2)}
"""

    provider = llm_cfg.get("provider", "gemini")
    model = llm_cfg.get("company_discovery_model", "gemini-2.0-flash-lite")

    companies = _call_llm_json_list(
        provider=provider,
        model=model,
        prompt=prompt,
    )
    discovered = _dedupe_companies(companies)

    if discovered:
        _save_cached_companies(cache_path, discovered)

    return discovered
