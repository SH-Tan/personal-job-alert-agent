import json
from openai import OpenAI

client = OpenAI()


def discover_related_companies(config: dict, profiles: dict) -> list[dict]:
    discovery_cfg = config.get("company_discovery", {})

    if not discovery_cfg.get("enabled", False):
        return []

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

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    companies = json.loads(resp.choices[0].message.content)

    return [
        {
            "name": c["name"],
            "careers_url": c.get("careers_url_guess", ""),
            "why_relevant": c.get("why_relevant", ""),
        }
        for c in companies
        if c.get("careers_url_guess")
    ]