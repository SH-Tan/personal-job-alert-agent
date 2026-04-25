# Personal Job Alert Agent

This project monitors company career pages and job-alert emails, matches opportunities against a single CV, and stores recent jobs in SQLite.

The configuration is designed to spend LLM credits only where they help most: CV extraction runs only when the CV profile cache is missing or stale, company discovery is cached after the first run, and per-job matching uses a local prefilter before calling Gemini.

## What It Does

1. Parses the CV at `data/*.pdf`.
2. Scrapes configured company career pages for internship-like postings.
3. Reads recent job-alert emails from IMAP when email sources are enabled.
4. Scores jobs against the configured search profile.
5. Stores matched jobs in `data/jobs.db`.
6. Prunes stored jobs older than 14 days by default.

## Project Layout

```text
.
├── main.py                    # Runs one scan immediately
├── view_jobs.py               # Lists saved jobs from SQLite
├── scheduler.py               # Runs the scan every 48 hours
├── config.yaml                # CV, company, matching, and cost controls
├── requirements.txt           # Python dependencies
├── agent/
│   ├── cv_profile.py          # CV parsing and profile cache
│   ├── sources.py             # Company page and email collection
│   ├── matcher.py             # Local or Gemini-based job scoring
│   ├── company_discovery.py   # Cached Gemini company suggestions
│   ├── storage.py             # SQLite persistence
│   └── notify.py              # Legacy email notification helper, unused by main.py
└── data/
    └── *.pdf     # Your CV
```

## Setup

Create and activate a Python environment, then install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env` in the project root:

```bash
GEMINI_API_KEY=your_gemini_key

EMAIL_ADDRESS=your_email@gmail.com
EMAIL_APP_PASSWORD=your_email_app_password

IMAP_HOST=imap.gmail.com
IMAP_PORT=993
```

For Gmail inbox access, `EMAIL_APP_PASSWORD` should be an app password, not your normal account password. SMTP settings are no longer needed because the agent does not send email.

## Configuration

The repo is currently configured for one CV:

```yaml
cvs:
  primary:
    path: data/*.pdf
    description: "Primary CV for internship and early-career job matching"
```

LLM cost controls live in `config.yaml`:

```yaml
llm:
  provider: gemini
  use_for_cv_profile: true
  use_for_company_discovery: true
  use_for_matching: true
  fallback_to_local: true
  cv_profile_model: gemini-2.0-flash-lite
  company_discovery_model: gemini-2.0-flash-lite
  matching_model: gemini-2.0-flash-lite
```

With these settings, Gemini is used carefully:

- `use_for_cv_profile: true` only calls Gemini when `data/profiles.json` needs to be created or rebuilt after a CV/config change.
- `use_for_company_discovery: true` only calls Gemini when company discovery is enabled and `data/discovered_companies.json` is missing or `refresh_cache: true`.
- `use_for_matching: true` still uses local prefiltering first; Gemini is called only for uncertain jobs.
- `fallback_to_local: true` lets the agent continue with local extraction/scoring if an LLM call is rate-limited or unavailable.

Recommended lower-cost mode is to set `use_for_matching: false`, because matching can scale with every new job.

Company discovery is controlled here:

```yaml
company_discovery:
  enabled: true
  cache_path: data/discovered_companies.json
  refresh_cache: false
```

Set `refresh_cache: true` for one run when you want a fresh Gemini-generated company list, then set it back to `false`.

Storage retention is controlled here:

```yaml
storage:
  retention_days: 14
```

The agent deletes older rows from `data/jobs.db` at the start of each run. Email alerts are filtered by email date before storage. Company career pages do not reliably expose original posting dates, so those rows are retained based on when the agent first collected them.

## Run Once

```bash
python main.py
```

The first run creates:

```text
data/jobs.db
data/profiles.json
data/discovered_companies.json
```

`profiles.json` is cached and reused until the CV file or CV config changes. `discovered_companies.json` is reused until you set `company_discovery.refresh_cache: true`.

Jobs are stored in SQLite only; no email notification is sent.

## View Saved Jobs

List recent saved jobs:

```bash
python view_jobs.py
```

Show full details for one job:

```bash
python view_jobs.py --id 12
```

Write the list to a CSV file:

```bash
python view_jobs.py --output data/jobs_export.csv
```

Write full structured data to JSON:

```bash
python view_jobs.py --format json --output data/jobs_export.json
```

Write one job detail to JSON:

```bash
python view_jobs.py --id 12 --format json --output data/job_12.json
```

The compact list shows ID, score, posted or collected time, company, and job name. The detail view shows name, company, link, posted time, collected time, source, score, reason, and description.

For company career pages, `posted_at` is usually unknown because most pages do not expose a dependable posting date. For email alerts, `posted_at` is the email message date.

## Run On A Schedule

```bash
python scheduler.py
```

The scheduler runs every 48 hours using the `America/New_York` timezone.

## Reducing LLM Cost

The low-cost mode is already enabled:

- CV profile extraction uses Gemini only on cache miss or cache invalidation.
- Company discovery uses Gemini only when its cache is missing or manually refreshed.
- Job matching uses local scoring first and only calls Gemini for uncertain jobs.
- Recent jobs are stored in SQLite, so repeated runs do not rematch old jobs.
- Stored jobs older than the retention window are pruned automatically.
- Career pages are scraped concurrently and deduplicated before matching.

Use Gemini selectively when you want better quality for a specific step. The most important setting to watch is `use_for_matching`, because that one can scale with new jobs found.
