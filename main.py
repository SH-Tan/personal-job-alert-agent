import yaml
from dotenv import load_dotenv

from agent.cv_profile import load_or_build_profiles
from agent.company_discovery import discover_related_companies
from agent.sources import collect_jobs
from agent.matcher import match_job_against_profiles
from agent.storage import init_db, exists, save_job, make_fingerprint
from agent.notify import send_email_notification


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    load_dotenv()

    config = load_config()
    db_path = "data/jobs.db"

    threshold = int(config.get("matching", {}).get("threshold", 75))
    notify_top_k = int(config.get("matching", {}).get("notify_top_k", 10))

    print("[INFO] Initializing DB...")
    init_db(db_path)

    print("[INFO] Loading CV profiles...")
    profiles = load_or_build_profiles(config)

    print("[INFO] Discovering related companies...")
    discovered = discover_related_companies(config, profiles)

    if discovered:
        print(f"[INFO] Discovered {len(discovered)} possible companies.")
        config["known_companies"] = config.get("known_companies", []) + discovered

    print("[INFO] Collecting jobs/posts/alerts...")
    jobs = collect_jobs(config)
    print(f"[INFO] Collected {len(jobs)} raw items.")

    notify_items = []

    for job in jobs:
        fp = make_fingerprint(job)

        if exists(db_path, fp):
            print(f"[SKIP] Already seen: {job.get('title')}")
            continue

        print(f"[INFO] Matching: {job.get('title')}")

        try:
            match = match_job_against_profiles(
                job=job,
                profiles=profiles,
                search_profiles=config.get("search_profiles", []),
            )
        except Exception as e:
            print(f"[WARN] Match failed: {e}")
            continue

        save_job(db_path, job, match)

        score = int(match.get("score", 0))

        if score >= threshold:
            notify_items.append(
                {
                    "job": job,
                    "match": match,
                }
            )

    notify_items.sort(
        key=lambda x: int(x["match"].get("score", 0)),
        reverse=True,
    )

    notify_items = notify_items[:notify_top_k]

    print(f"[INFO] Sending {len(notify_items)} notifications...")
    send_email_notification(notify_items)


if __name__ == "__main__":
    main()