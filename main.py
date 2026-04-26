import yaml
from dotenv import load_dotenv

from agent.cv_profile import load_or_build_profiles
from agent.company_discovery import discover_related_companies, save_company_registry
from agent.sources import collect_jobs
from agent.matcher import match_job_against_profiles
from agent.storage import (
    init_db,
    load_seen_fingerprints,
    make_fingerprint,
    prune_old_jobs,
    save_job,
)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _merge_companies(*company_lists: list[dict]) -> list[dict]:
    merged = []
    seen = set()

    for company_list in company_lists:
        for company in company_list:
            key = (
                str(company.get("name", "")).strip().lower(),
                str(company.get("careers_url", "")).strip().lower(),
            )

            if not key[0] or not key[1] or key in seen:
                continue

            seen.add(key)
            merged.append(company)

    return merged


def main():
    load_dotenv()

    config = load_config()
    db_path = "data/jobs.db"
    storage_cfg = config.get("storage", {})

    threshold = int(config.get("matching", {}).get("threshold", 75))
    retention_days = int(storage_cfg.get("retention_days", 14))

    print("[INFO] Initializing DB...")
    init_db(db_path)
    deleted_count = prune_old_jobs(db_path, retention_days)

    if deleted_count:
        print(f"[INFO] Pruned {deleted_count} stored jobs older than {retention_days} days.")

    seen_fingerprints = load_seen_fingerprints(db_path)

    print("[INFO] Loading CV profiles...")
    profiles = load_or_build_profiles(config)

    print("[INFO] Discovering related companies...")
    discovered = discover_related_companies(config, profiles)

    if discovered:
        print(f"[INFO] Discovered {len(discovered)} possible companies.")
    config["known_companies"] = _merge_companies(
        config.get("known_companies", []),
        discovered,
    )
    save_company_registry(
        config.get("company_discovery", {}).get("all_companies_path", "data/all_companies.json"),
        config["known_companies"],
    )

    print("[INFO] Collecting jobs/posts/alerts...")
    jobs = collect_jobs(config)
    print(f"[INFO] Collected {len(jobs)} raw items.")
    saved_count = 0
    high_score_count = 0

    for job in jobs:
        fp = make_fingerprint(job)

        if fp in seen_fingerprints:
            print(f"[SKIP] Already seen: {job.get('title')}")
            continue

        print(f"[INFO] Matching: {job.get('title')}")

        try:
            match = match_job_against_profiles(
                job=job,
                profiles=profiles,
                search_profiles=config.get("search_profiles", []),
                config=config,
            )
        except Exception as e:
            print(f"[WARN] Match failed: {e}")
            continue

        save_job(db_path, job, match)
        seen_fingerprints.add(fp)
        saved_count += 1

        score = int(match.get("score", 0))

        if score >= threshold:
            high_score_count += 1

    print(
        f"[INFO] Saved {saved_count} new jobs. "
        f"{high_score_count} matched the threshold >= {threshold}."
    )
    print("[INFO] Email notifications are disabled; jobs are stored in SQLite only.")


if __name__ == "__main__":
    main()
