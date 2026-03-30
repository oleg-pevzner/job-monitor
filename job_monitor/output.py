"""Output formatting for CLI commands.

Supports json, table, csv, and quiet modes. Auto-detects TTY for default format.
"""

from __future__ import annotations

import csv
import io
import json
import sys


def detect_format(explicit: str | None) -> str:
    """Return the output format: explicit choice, or auto-detect from TTY."""
    if explicit:
        return explicit
    return "table" if sys.stdout.isatty() else "json"


def format_jobs(jobs: list[dict], fmt: str) -> str:
    """Format a list of job dicts for output."""
    if fmt == "json":
        return json.dumps(jobs, indent=2, default=str)
    if fmt == "csv":
        return _format_csv(jobs)
    if fmt == "quiet":
        return f"{len(jobs)} jobs"
    return _format_table(jobs)


def format_result(result: dict, fmt: str) -> str:
    """Format a pipeline result dict for output."""
    if fmt == "json":
        return json.dumps(result, indent=2, default=str)
    if fmt == "quiet":
        return f"{result.get('new', 0)} new jobs"
    # table/default: human-readable summary
    lines = []
    if "searched" in result:
        lines.append(f"searched {result.get('sources', '?')} sources, {result['searched']} results")
    if "new" in result:
        lines.append(f"deduped to {result['new']} new jobs")
    if "stored" in result:
        lines.append(f"stored {result['stored']} jobs in {result.get('db_path', 'database')}")
    if result.get("emailed"):
        lines.append(f"emailed digest to {result.get('email_to', '?')}")
    if result.get("dry_run"):
        lines.append("no changes made (dry run)")
    return "\n".join(lines)


def _format_table(jobs: list[dict]) -> str:
    """Format jobs as a human-readable table."""
    if not jobs:
        return "no jobs found"
    lines = []
    for job in jobs:
        title = job.get("title", "?")
        company = job.get("company", "?")
        parts = [f"  {title} - {company}"]
        details = []
        if job.get("location"):
            details.append(job["location"])
        if job.get("salary"):
            details.append(job["salary"])
        if details:
            parts.append(f"  {' | '.join(details)}")
        if job.get("url"):
            parts.append(f"  {job['url']}")
        lines.append("\n".join(parts))
    header = f"found {len(jobs)} jobs:\n"
    return header + "\n\n".join(lines)


def _format_csv(jobs: list[dict]) -> str:
    """Format jobs as CSV."""
    if not jobs:
        return ""
    fields = ["title", "company", "location", "salary", "seniority", "url", "source_query"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(jobs)
    return buf.getvalue()
