"""SQLite storage backend. Zero configuration, works out of the box."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path


DB_FIELDS = {
    "url", "title", "company", "company_url", "location", "salary", "seniority",
    "source_query", "snippet", "applicant_count", "status",
    "dm_name", "dm_title", "dm_email", "dm_email_status", "dm_source",
    "title_company_key",
}

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    company TEXT,
    company_url TEXT,
    location TEXT,
    salary TEXT,
    seniority TEXT,
    source_query TEXT,
    snippet TEXT,
    applicant_count TEXT,
    status TEXT DEFAULT 'new',
    title_company_key TEXT,
    dm_name TEXT,
    dm_title TEXT,
    dm_email TEXT,
    dm_email_status TEXT,
    dm_source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_jobs_tc_key ON jobs(title_company_key);
"""


class SQLiteStorage:
    """SQLite-backed job storage. Auto-creates DB and table on init."""

    def __init__(self, db_path: str = "./jobs.db"):
        self.db_path = str(Path(db_path).resolve())
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(CREATE_TABLE)
        self._conn.execute(CREATE_INDEX)
        self._conn.commit()

    def get_existing_urls(self, urls: list[str]) -> set[str]:
        if not urls:
            return set()
        result = set()
        for i in range(0, len(urls), 100):
            batch = urls[i:i + 100]
            placeholders = ",".join("?" * len(batch))
            cursor = self._conn.execute(
                f"SELECT url FROM jobs WHERE url IN ({placeholders})", batch
            )
            result.update(row["url"] for row in cursor)
        return result

    def get_existing_keys(self, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        result = set()
        for i in range(0, len(keys), 100):
            batch = keys[i:i + 100]
            placeholders = ",".join("?" * len(batch))
            cursor = self._conn.execute(
                f"SELECT title_company_key FROM jobs WHERE title_company_key IN ({placeholders})",
                batch,
            )
            result.update(row["title_company_key"] for row in cursor if row["title_company_key"])
        return result

    def insert_jobs(self, jobs: list[dict]) -> None:
        if not jobs:
            return
        for job in jobs:
            row = {k: v for k, v in {**job, "status": "new"}.items() if k in DB_FIELDS}
            cols = list(row.keys())
            placeholders = ",".join("?" * len(cols))
            col_names = ",".join(cols)
            self._conn.execute(
                f"INSERT OR IGNORE INTO jobs ({col_names}) VALUES ({placeholders})",
                [row[c] for c in cols],
            )
        self._conn.commit()
        print(f"stored {len(jobs)} new postings")

    def list_jobs(self, since_days: int | None = None, status: str | None = None) -> list[dict]:
        query = "SELECT * FROM jobs WHERE 1=1"
        params: list = []
        if since_days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
            query += " AND created_at >= ?"
            params.append(cutoff)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        cursor = self._conn.execute(query, params)
        return [dict(row) for row in cursor]

    def count(self) -> int:
        cursor = self._conn.execute("SELECT COUNT(*) as cnt FROM jobs")
        return cursor.fetchone()["cnt"]

    def close(self):
        self._conn.close()
