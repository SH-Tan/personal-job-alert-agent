import json
from pathlib import Path
from pypdf import PdfReader
from openai import OpenAI

client = OpenAI()


def pdf_to_text(path: str) -> str:
    reader = PdfReader(path)
    pages = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)

    return "\n".join(pages)


def extract_profile_from_cv(cv_text: str, cv_name: str, cv_description: str) -> dict:
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

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )

    return json.loads(response.choices[0].message.content)


def load_or_build_profiles(config: dict, cache_path: str = "data/profiles.json") -> dict:
    cache = Path(cache_path)

    if cache.exists():
        with open(cache, "r") as f:
            return json.load(f)

    profiles = {}

    for cv_name, cv_info in config["cvs"].items():
        cv_text = pdf_to_text(cv_info["path"])

        profile = extract_profile_from_cv(
            cv_text=cv_text,
            cv_name=cv_name,
            cv_description=cv_info.get("description", ""),
        )

        profiles[cv_name] = profile

    cache.parent.mkdir(parents=True, exist_ok=True)

    with open(cache, "w") as f:
        json.dump(profiles, f, indent=2)

    return profiles