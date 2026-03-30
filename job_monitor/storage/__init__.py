"""Storage backend protocol and factory."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Interface for job storage backends."""

    def get_existing_urls(self, urls: list[str]) -> set[str]:
        """Return the subset of URLs that already exist in storage."""
        ...

    def get_existing_keys(self, keys: list[str]) -> set[str]:
        """Return the subset of title_company_keys that already exist."""
        ...

    def insert_jobs(self, jobs: list[dict]) -> None:
        """Insert new job postings into storage."""
        ...

    def list_jobs(self, since_days: int | None = None, status: str | None = None) -> list[dict]:
        """Query stored jobs with optional filters."""
        ...

    def count(self) -> int:
        """Return total number of stored jobs."""
        ...


def create_storage(config: dict) -> StorageBackend:
    """Create a storage backend from config."""
    storage_config = config.get("storage", {})
    backend = storage_config.get("backend", "sqlite")

    if backend == "supabase":
        from job_monitor.storage.supabase import SupabaseStorage
        return SupabaseStorage(config)

    from job_monitor.storage.sqlite import SQLiteStorage
    path = storage_config.get("path", "./jobs.db")
    return SQLiteStorage(path)
