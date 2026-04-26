import json
from pathlib import Path
from typing import Any

import os
import requests
from urllib.parse import urlparse


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
        "homepage_url": str(company.get("homepage_url") or "").strip(),
        "why_relevant": str(company.get("why_relevant", "")).strip(),
        "company_size": str(company.get("company_size") or "").strip(),
        "discovery_source": str(company.get("discovery_source") or "").strip(),
        "careers_url_status": str(company.get("careers_url_status") or "").strip(),
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


def _normalize_url(url: str) -> str:
    url = (url or "").strip()

    if not url:
        return ""

    if url.startswith("//"):
        return "https:" + url

    if "://" not in url:
        return "https://" + url.lstrip("/")

    return url


def _candidate_careers_urls(company: dict[str, str]) -> list[str]:
    candidates = []

    for raw_url in (company.get("careers_url", ""), company.get("homepage_url", "")):
        url = _normalize_url(raw_url)
        if not url:
            continue

        candidates.append(url)

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            continue

        origin = f"{parsed.scheme}://{parsed.netloc}"
        candidates.extend(
            [
                origin,
                f"{origin}/careers",
                f"{origin}/careers/",
                f"{origin}/jobs",
                f"{origin}/jobs/",
                f"{origin}/careers/jobs",
                f"{origin}/students",
                f"{origin}/students/",
                f"{origin}/students-and-graduates",
                f"{origin}/early-careers",
                f"{origin}/campus",
            ]
        )

    deduped = []
    seen = set()

    for url in candidates:
        normalized = _normalize_url(url).rstrip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    return deduped


def _validate_company_urls(companies: list[dict[str, str]]) -> list[dict[str, str]]:
    validated = []
    headers = {"User-Agent": "Mozilla/5.0 personal-job-alert-agent/1.0"}

    for company in companies:
        chosen_url = ""
        status = "unreadable"

        for candidate_url in _candidate_careers_urls(company):
            try:
                response = requests.get(
                    candidate_url,
                    headers=headers,
                    timeout=15,
                    allow_redirects=True,
                )
                response.raise_for_status()
            except Exception:
                continue

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                continue

            page_lower = response.text[:10000].lower()
            if not any(
                token in page_lower
                for token in ("career", "careers", "job", "jobs", "intern", "student")
            ):
                continue

            chosen_url = response.url
            status = "validated"
            break

        if not chosen_url:
            chosen_url = _normalize_url(company.get("careers_url") or company.get("homepage_url", ""))
            print(f"[WARN] Keeping discovered company with unreadable careers page: {company['name']}")

        validated.append(
            {
                "name": company["name"],
                "careers_url": chosen_url,
                "homepage_url": company.get("homepage_url", ""),
                "why_relevant": company.get("why_relevant", ""),
                "company_size": company.get("company_size", ""),
                "discovery_source": company.get("discovery_source", "llm_discovery"),
                "careers_url_status": status,
            }
        )

    return validated


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


def save_company_registry(path: str, companies: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with open(target, "w", encoding="utf-8") as f:
        json.dump(_dedupe_companies(companies), f, indent=2)


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
    focus_areas = discovery_cfg.get(
        "focus_areas",
        [
            "machine learning",
            "AI research",
            "robotics",
            "autonomous vehicles",
            "finance",
            "quant trading",
            "quant research",
            "software engineering internships",
        ],
    )
    company_size_preference = discovery_cfg.get(
        "company_size_preference",
        [
            "small startups",
            "mid-size companies",
            "select larger companies",
        ],
    )

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
- {json.dumps(focus_areas, indent=2)}

Prioritize:
- stable top-level careers pages, not job-search result pages
- companies with internships, university recruiting, or student programs
- a mix of AI, autonomy, finance, and quant firms when relevant
- include smaller startups and mid-size companies, not only famous large companies

Return JSON only:
[
  {{
    "name": "Company name",
    "why_relevant": "...",
    "company_size": "startup | mid-size | large",
    "homepage_url": "https://company.com",
    "careers_url_guess": "https://company.com/careers"
  }}
]

Max companies: {max_companies}

Seed keywords:
{json.dumps(seed_keywords, indent=2)}

Candidate profiles:
{json.dumps(profile_summaries, indent=2)}

Preferred company sizes:
{json.dumps(company_size_preference, indent=2)}
"""

    provider = llm_cfg.get("provider", "gemini")
    model = llm_cfg.get("company_discovery_model", "gemini-2.0-flash-lite")

    companies = _call_llm_json_list(
        provider=provider,
        model=model,
        prompt=prompt,
    )
    discovered = _validate_company_urls(_dedupe_companies(companies))

    if discovered:
        _save_cached_companies(cache_path, discovered)

    return discovered
