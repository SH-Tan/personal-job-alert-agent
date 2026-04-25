import json
from openai import OpenAI

client = OpenAI()


def match_job_against_profiles(
    job: dict,
    profiles: dict,
    search_profiles: list[dict],
) -> dict:
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

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )

    return json.loads(resp.choices[0].message.content)