import sqlite3
from datetime import datetime


def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
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
            created_at TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def make_fingerprint(job: dict) -> str:
    url = job.get("url", "").strip().lower()
    company = job.get("company", "").strip().lower()
    title = job.get("title", "").strip().lower()

    if url:
        return url

    return f"{company}::{title}"


def exists(db_path: str, fingerprint: str) -> bool:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id FROM jobs WHERE fingerprint = ?", (fingerprint,))
    row = cur.fetchone()

    conn.close()
    return row is not None


def save_job(db_path: str, job: dict, match: dict):
    conn = sqlite3.connect(db_path)
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
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    conn.commit()
    conn.close()