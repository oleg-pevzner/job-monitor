"""Supabase (cloud Postgres) storage backend."""

from __future__ import annotations

import os

DB_FIELDS = {
    "url", "title", "company", "company_url", "location", "salary", "seniority",
    "source_query", "snippet", "applicant_count", "status",
    "dm_name", "dm_title", "dm_email", "dm_email_status", "dm_source",
    "title_company_key",
}


class SupabaseStorage:
    """Supabase-backed job storage.

    Requires SUPABASE_URL and SUPABASE_KEY environment variables.
    Install with: pip install job-monitor[supabase]
    """

    def __init__(self, config: dict):
        try:
            from supabase import create_client
        except ImportError:
            raise ImportError(
                "Supabase backend requires the supabase package. "
                "Install with: pip install job-monitor[supabase]"
            )
        storage_config = config.get("storage", {})
        self.table_name = storage_config.get("table", "jobs")
        url = os.environ.get("SUPABASE_URL") or storage_config.get("url", "")
        key = os.environ.get("SUPABASE_KEY") or storage_config.get("key", "")
        if not url or not key:
            raise ValueError(
                "Supabase backend requires SUPABASE_URL and SUPABASE_KEY environment variables"
            )
        self._client = create_client(url, key)

    def get_existing_urls(self, urls: list[str]) -> set[str]:
        if not urls:
            return set()
        result = set()
        for i in range(0, len(urls), 100):
            batch = urls[i:i + 100]
            resp = self._client.table(self.table_name).select("url").in_("url", batch).execute()
            result.update(row["url"] for row in resp.data)
        return result

    def get_existing_keys(self, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        result = set()
        for i in range(0, len(keys), 100):
            batch = keys[i:i + 100]
            resp = (self._client.table(self.table_name)
                    .select("title_company_key")
                    .in_("title_company_key", batch)
                    .execute())
            result.update(
                row["title_company_key"] for row in resp.data if row.get("title_company_key")
            )
        return result

    def insert_jobs(self, jobs: list[dict]) -> None:
        if not jobs:
            return
        rows = [{k: v for k, v in {**job, "status": "new"}.items() if k in DB_FIELDS} for job in jobs]
        self._client.table(self.table_name).insert(rows).execute()
        print(f"stored {len(jobs)} new postings")

    def list_jobs(self, since_days: int | None = None, status: str | None = None) -> list[dict]:
        query = self._client.table(self.table_name).select("*")
        if status:
            query = query.eq("status", status)
        query = query.order("created_at", desc=True)
        if since_days is not None:
            query = query.limit(1000)
        resp = query.execute()
        return resp.data

    def count(self) -> int:
        resp = self._client.table(self.table_name).select("url", count="exact").execute()
        return resp.count or 0
