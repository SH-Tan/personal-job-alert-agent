# Personal Job Alert Agent

A small Python agent that checks company career pages and job-alert emails, matches jobs against your CV/search profile, and stores recent matches in SQLite. It does not send email notifications.

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

`playwright install chromium` is needed for JavaScript-heavy career sites such as Workday, Greenhouse, and Lever. If you skip it, the agent will still scan normal HTML pages and log a warning when a browser-rendered site cannot be scraped.

Create `.env`:

```bash
GEMINI_API_KEY=your_gemini_key

EMAIL_ADDRESS=your_email@outlook.com
EMAIL_APP_PASSWORD=your_outlook_app_password
IMAP_HOST=outlook.office365.com
IMAP_PORT=993
IMAP_FOLDER=INBOX
```

Run one scan:

```bash
python main.py
```

View saved jobs:

```bash
python view_jobs.py
python view_jobs.py --id 12
python view_jobs.py --output data/jobs_export.csv
python view_jobs.py --format json --output data/jobs_export.json
```

Run every 48 hours:

```bash
python scheduler.py
```

## Sample `config.yaml`

Keep your real `config.yaml` local. It is ignored by git because it may contain personal job targets, CV paths, and company lists.

```yaml
cvs:
  primary:
    path: data/my_cv.pdf
    description: "Primary CV for internship and early-career job matching"

llm:
  provider: gemini
  use_for_cv_profile: false
  use_for_company_discovery: true
  use_for_matching: true
  fallback_to_local: true
  cv_profile_model: gemini-2.5-flash-lite
  company_discovery_model: gemini-2.5-flash-lite
  matching_model: gemini-2.5-flash-lite

search_profiles:
  - name: "Target internships"
    cv: primary
    keywords:
      - machine learning intern
      - AI research intern
      - software engineering intern
      - robotics intern
    target_jobs:
      - Machine Learning Intern
      - AI Research Intern
      - Software Engineering Intern
      - Robotics Research Intern

company_discovery:
  enabled: true
  cache_path: data/discovered_companies.json
  all_companies_path: data/all_companies.json
  refresh_cache: false
  focus_areas:
    - machine learning
    - AI research
    - robotics
    - autonomous vehicles
    - finance technology
    - quantitative trading
    - quantitative research
  company_size_preference:
    - small startups
    - mid-size companies
    - select larger companies
  seed_keywords:
    - machine learning internship
    - AI research internship
    - software engineering internship
  max_companies_per_run: 20

known_companies:
  - name: Example Company
    careers_url: https://example.com/careers

email_sources:
  enabled: true
  max_recent_emails: 80
  imap_folder: INBOX
  sender_keywords:
    - linkedin
    - handshake
    - greenhouse
    - lever
    - workday
  content_keywords:
    - intern
    - internship
    - machine learning
    - software engineering

matching:
  threshold: 75

storage:
  retention_days: 14
```

## How It Saves Cost

- CV extraction is cached in `data/profiles.json`.
- Company discovery is cached in `data/discovered_companies.json`.
- All merged companies are written to `data/all_companies.json`, even if no job is found for them yet.
- Set `company_discovery.refresh_cache: true` for one run if you want to rebuild discovered companies after changing focus areas or seed keywords.
- Matching uses local scoring first and only calls Gemini for uncertain jobs.
- Set `llm.use_for_matching: false` for the cheapest matching mode.

## Stored Data

Jobs are saved in `data/jobs.db`. Rows older than `storage.retention_days` are pruned at the start of each run.

`view_jobs.py` shows name, company, link, score, posted time when available, and collection time. Email alerts can provide a real posted time from the email date; company career pages often cannot, so the agent uses collection time there.

## Privacy

`.env`, `config.yaml`, and `data/` are ignored by git. If secrets were ever committed or pushed, rotate those keys because removing files later does not remove them from git history.

## Outlook Notes

If you use Outlook/Hotmail/Live instead of Gmail, use:

```bash
EMAIL_ADDRESS=your_email@outlook.com
EMAIL_APP_PASSWORD=your_outlook_app_password
IMAP_HOST=outlook.office365.com
IMAP_PORT=993
IMAP_FOLDER=INBOX
```

If Microsoft account two-step verification is enabled, create an app password and use that for `EMAIL_APP_PASSWORD`. If Outlook moves alerts into a custom folder, set `IMAP_FOLDER` to that folder name instead of `INBOX`.
