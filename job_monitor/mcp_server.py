"""MCP stdio server for job-monitor.

Exposes job-monitor capabilities as MCP tools that AI agents can discover
and call directly. Start with: job-monitor mcp

Tools:
  search_jobs      - Search job boards for matching postings
  dedup_jobs       - Filter out previously seen jobs
  store_jobs       - Save jobs to the database
  list_jobs        - Query stored jobs
  run_monitor      - Run the full pipeline from a config file
  validate_config  - Check a config file for errors
"""

from __future__ import annotations

import json
import os


def serve():
    """Start the MCP stdio server."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("error: MCP server requires the mcp package")
        print("  pip install job-monitor[mcp]")
        raise SystemExit(1)

    mcp = FastMCP("job-monitor")

    @mcp.tool()
    def search_jobs(
        queries: list[str],
        locations: list[str],
        sources: list[str] | None = None,
        title_keywords: list[str] | None = None,
        title_exclude: list[str] | None = None,
        jobs_per_search: int = 10,
    ) -> str:
        """Search job boards for matching postings.

        Args:
            queries: Job search queries, e.g. ["Software Engineer", "Backend Engineer"]
            locations: Locations to search, e.g. ["San Francisco Bay Area", "New York"]
            sources: Job boards to search. Options: linkedin, indeed, usajobs, google_jobs. Default: ["linkedin"]
            title_keywords: Required keywords in job title for filtering
            title_exclude: Keywords to exclude from job titles
            jobs_per_search: Number of results per query/location combo (default: 10)

        Returns:
            JSON array of job objects with title, company, location, salary, url, etc.
        """
        from dotenv import load_dotenv
        load_dotenv()

        apify_token = os.environ.get("APIFY_API_TOKEN")
        if not apify_token:
            return json.dumps({"error": "APIFY_API_TOKEN not set. Get one at https://console.apify.com/sign-up"})

        from job_monitor.sources import search_all_sources
        from job_monitor.dedup import dedup_by_title_company

        config = {
            "search_queries": queries,
            "locations": locations,
            "sources": sources or ["linkedin"],
            "jobs_per_search": jobs_per_search,
            "filters": {
                "title_keywords": title_keywords or [],
                "title_exclude": title_exclude or [],
                "company_exclude": [],
                "location_allow": [],
                "location_exclude": [],
                "salary_max_annual": None,
            },
        }

        jobs = search_all_sources(apify_token, config)
        jobs = dedup_by_title_company(jobs)
        return json.dumps(jobs, default=str)

    @mcp.tool()
    def dedup_jobs(jobs_json: str, db_path: str = "./jobs.db") -> str:
        """Filter out previously seen jobs against the local database.

        Args:
            jobs_json: JSON string of job array (from search_jobs output)
            db_path: Path to SQLite database (default: ./jobs.db)

        Returns:
            JSON array of only new (unseen) jobs.
        """
        from job_monitor.storage.sqlite import SQLiteStorage
        from job_monitor.dedup import dedup_by_title_company, dedup_against_storage

        jobs = json.loads(jobs_json) if isinstance(jobs_json, str) else jobs_json
        jobs = dedup_by_title_company(jobs)
        storage = SQLiteStorage(db_path)
        new_jobs = dedup_against_storage(storage, jobs)
        return json.dumps(new_jobs, default=str)

    @mcp.tool()
    def store_jobs(jobs_json: str, db_path: str = "./jobs.db") -> str:
        """Save jobs to the SQLite database.

        Args:
            jobs_json: JSON string of job array to store
            db_path: Path to SQLite database (default: ./jobs.db)

        Returns:
            JSON object with stored count.
        """
        from job_monitor.storage.sqlite import SQLiteStorage

        jobs = json.loads(jobs_json) if isinstance(jobs_json, str) else jobs_json
        storage = SQLiteStorage(db_path)
        storage.insert_jobs(jobs)
        return json.dumps({"stored": len(jobs), "db_path": db_path})

    @mcp.tool()
    def list_jobs(db_path: str = "./jobs.db", since_days: int | None = None,
                  status: str | None = None) -> str:
        """Query stored jobs from the database.

        Args:
            db_path: Path to SQLite database (default: ./jobs.db)
            since_days: Only return jobs from the last N days
            status: Filter by status (e.g. "new")

        Returns:
            JSON array of stored job objects.
        """
        from job_monitor.storage.sqlite import SQLiteStorage

        storage = SQLiteStorage(db_path)
        jobs = storage.list_jobs(since_days=since_days, status=status)
        return json.dumps(jobs, default=str)

    @mcp.tool()
    def run_monitor(config_path: str, dry_run: bool = False) -> str:
        """Run the full job monitor pipeline from a config file.

        Executes: search -> dedup -> store -> notify (unless dry_run).

        Args:
            config_path: Path to YAML config file
            dry_run: If true, search and dedup but don't store or send emails

        Returns:
            JSON object with counts (searched, new, stored) and job list.
        """
        from job_monitor.config import load_config
        from job_monitor.pipeline import run

        config = load_config(config_path)
        result = run(config, dry_run=dry_run)
        return json.dumps(result, default=str)

    @mcp.tool()
    def validate_config(config_path: str) -> str:
        """Check a YAML config file for errors.

        Args:
            config_path: Path to YAML config file

        Returns:
            JSON object with valid (bool), sources, query count, location count.
        """
        try:
            from job_monitor.config import load_config
            config = load_config(config_path)
            return json.dumps({
                "valid": True,
                "sources": config.get("sources", []),
                "queries": len(config.get("search_queries", [])),
                "locations": len(config.get("locations", [])),
            })
        except SystemExit:
            return json.dumps({"valid": False, "error": "config validation failed"})
        except Exception as e:
            return json.dumps({"valid": False, "error": str(e)})

    mcp.run(transport="stdio")
