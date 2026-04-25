import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_db(db_path: str):
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT UNIQUE,
                source TEXT,
                company TEXT,
                title TEXT,
                url TEXT,
                description TEXT,
                matched_cv TEXT,
                search_profile TEXT,
                score INTEGER,
                reason TEXT,
                posted_at TEXT,
                created_at TEXT
            )
            """
        )
        cur.execute("PRAGMA table_info(jobs)")
        existing_columns = {row[1] for row in cur.fetchall()}

        if "posted_at" not in existing_columns:
            cur.execute("ALTER TABLE jobs ADD COLUMN posted_at TEXT")

        conn.commit()


def make_fingerprint(job: dict) -> str:
    url = job.get("url", "").strip().lower()
    company = job.get("company", "").strip().lower()
    title = job.get("title", "").strip().lower()

    if url:
        return url

    return f"{company}::{title}"


def exists(db_path: str, fingerprint: str) -> bool:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM jobs WHERE fingerprint = ?", (fingerprint,))
        row = cur.fetchone()
        return row is not None


def load_seen_fingerprints(db_path: str) -> set[str]:
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT fingerprint FROM jobs")
        return {row[0] for row in cur.fetchall() if row and row[0]}


def prune_old_jobs(db_path: str, retention_days: int) -> int:
    cutoff = datetime.now() - timedelta(days=retention_days)

    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM jobs WHERE created_at < ?",
            (cutoff.isoformat(timespec="seconds"),),
        )
        deleted_count = cur.rowcount
        conn.commit()

    return deleted_count


def save_job(db_path: str, job: dict, match: dict):
    with _connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO jobs
            (
                fingerprint,
                source,
                company,
                title,
                url,
                description,
                matched_cv,
                search_profile,
                score,
                reason,
                posted_at,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                make_fingerprint(job),
                job.get("source", ""),
                job.get("company", ""),
                match.get("title") or job.get("title", ""),
                job.get("url", ""),
                job.get("description", ""),
                match.get("matched_cv", ""),
                match.get("search_profile", ""),
                int(match.get("score", 0)),
                match.get("reason", ""),
                job.get("posted_at", ""),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
