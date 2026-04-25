import argparse
import csv
import json
import sqlite3
from pathlib import Path
from textwrap import shorten
from typing import Any


DB_PATH = "data/jobs.db"


def _connect(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}. Run python main.py first.")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def fetch_jobs(db_path: str, limit: int) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                title,
                company,
                url,
                score,
                posted_at,
                created_at
            FROM jobs
            ORDER BY COALESCE(posted_at, created_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def fetch_job(db_path: str, job_id: int) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                id,
                title,
                company,
                url,
                source,
                score,
                matched_cv,
                search_profile,
                reason,
                posted_at,
                created_at,
                description
            FROM jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()

    return _row_to_dict(row) if row is not None else None


def list_jobs(db_path: str, limit: int) -> None:
    jobs = fetch_jobs(db_path, limit)

    if not jobs:
        print("No jobs stored yet.")
        return

    print(f"{'ID':>4}  {'Score':>5}  {'Posted/Collected':<19}  {'Company':<24}  Job")
    print("-" * 100)

    for job in jobs:
        shown_time = job["posted_at"] or job["created_at"] or ""
        company = shorten(job["company"] or "", width=24, placeholder="...")
        title = shorten(job["title"] or "", width=60, placeholder="...")
        print(f"{job['id']:>4}  {job['score']:>5}  {shown_time[:19]:<19}  {company:<24}  {title}")


def show_job(db_path: str, job_id: int) -> None:
    job = fetch_job(db_path, job_id)

    if job is None:
        print(f"No job found with id {job_id}.")
        return

    fields = [
        ("ID", job["id"]),
        ("Name", job["title"]),
        ("Company", job["company"]),
        ("Link", job["url"]),
        ("Posted time", job["posted_at"] or "Unknown"),
        ("Collected time", job["created_at"]),
        ("Source", job["source"]),
        ("Score", job["score"]),
        ("CV", job["matched_cv"]),
        ("Search profile", job["search_profile"]),
        ("Reason", job["reason"]),
    ]

    for label, value in fields:
        print(f"{label}: {value}")

    print("\nDescription:")
    print(job["description"] or "")


def write_jobs_file(
    db_path: str,
    output_path: str,
    output_format: str,
    limit: int,
    job_id: int | None,
) -> None:
    if job_id is None:
        records = fetch_jobs(db_path, limit)
    else:
        job = fetch_job(db_path, job_id)
        records = [job] if job is not None else []

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        with open(output, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
    else:
        fieldnames = [
            "id",
            "title",
            "company",
            "url",
            "posted_at",
            "created_at",
            "source",
            "score",
            "matched_cv",
            "search_profile",
            "reason",
            "description",
        ]

        with open(output, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for record in records:
                writer.writerow({key: record.get(key, "") for key in fieldnames})

    print(f"Wrote {len(records)} job(s) to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="View jobs saved by the job alert agent.")
    parser.add_argument("--db", default=DB_PATH, help=f"SQLite database path. Default: {DB_PATH}")
    parser.add_argument("--limit", type=int, default=25, help="Number of jobs to list.")
    parser.add_argument("--id", type=int, help="Show full details for one job ID.")
    parser.add_argument("--output", help="Write jobs to this file instead of printing only.")
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Output file format. Default: csv.",
    )
    args = parser.parse_args()

    if args.output:
        write_jobs_file(args.db, args.output, args.format, args.limit, args.id)
        return

    if args.id is not None:
        show_job(args.db, args.id)
    else:
        list_jobs(args.db, args.limit)


if __name__ == "__main__":
    main()
