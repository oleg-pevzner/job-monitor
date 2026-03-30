"""Three-layer job deduplication.

Layer 1: Cross-source dedup by normalized title+company key
Layer 2: Database dedup against stored URLs and title+company keys
Layer 3: Company proximity dedup (one job per company, prefer priority locations)
"""

from __future__ import annotations

import re
from collections import defaultdict


def normalize_company(name: str) -> str:
    """Normalize company name for fuzzy matching.

    Strips corporate suffixes then removes all non-alphanumeric characters
    so that variants like "Life Time" and "Lifetime" collapse to the same key.
    """
    s = name.lower().strip()
    s = re.sub(r'\b(inc\.?|llc\.?|corp\.?|co\.?|ltd\.?|l\.?p\.?|corporation|incorporated|company|group)\s*$', '', s)
    s = re.sub(r'[^a-z0-9]', '', s)
    return s


def normalize_title(title: str) -> str:
    """Normalize job title for fuzzy matching.

    Strips trailing parentheticals like (Part-Time), trailing location
    qualifiers after a spaced dash, then removes all non-alphanumeric characters.
    """
    s = title.lower().strip()
    s = re.sub(r'\s*\([^)]*\)\s*$', '', s)
    s = re.sub(r'\s+-\s+[a-z, ]+$', '', s)
    s = re.sub(r'[^a-z0-9]', '', s)
    return s


def make_title_company_key(title: str, company: str) -> str:
    """Build a stable dedup key from title + company."""
    return f"{normalize_company(company)}|{normalize_title(title)}"


def dedup_by_title_company(jobs: list[dict]) -> list[dict]:
    """Remove jobs with the same normalized title+company, keeping first occurrence.

    Stamps each job with its title_company_key for downstream use.
    """
    seen = set()
    result = []
    for job in jobs:
        company = job.get("company", "")
        if not company:
            result.append(job)
            continue
        key = make_title_company_key(job.get("title", ""), company)
        job["title_company_key"] = key
        if key not in seen:
            seen.add(key)
            result.append(job)

    dropped = len(jobs) - len(result)
    if dropped:
        print(f"title+company dedup: kept {len(result)}, dropped {dropped} cross-source duplicates")
    return result


def dedup_against_storage(storage, jobs: list[dict]) -> list[dict]:
    """Return only jobs whose URLs or title+company keys aren't already stored."""
    if not jobs:
        return []

    urls = [j["url"] for j in jobs]
    existing_urls = storage.get_existing_urls(urls)

    tc_keys = [j["title_company_key"] for j in jobs if j.get("title_company_key")]
    existing_keys = storage.get_existing_keys(tc_keys) if tc_keys else set()

    new_jobs = []
    for j in jobs:
        if j["url"] in existing_urls:
            continue
        if j.get("title_company_key") and j["title_company_key"] in existing_keys:
            continue
        new_jobs.append(j)

    existing_count = len(jobs) - len(new_jobs)
    print(f"dedup: {len(jobs)} total, {existing_count} existing, {len(new_jobs)} new")
    return new_jobs


def dedup_by_company_proximity(jobs: list[dict], location_priority: list[str]) -> list[dict]:
    """Keep one job per company, preferring locations earlier in location_priority."""
    if not location_priority:
        return jobs

    priority_lower = [loc.lower() for loc in location_priority]

    def location_rank(job):
        loc = (job.get("location") or "").lower()
        for i, p in enumerate(priority_lower):
            if p in loc:
                return i
        return len(priority_lower)

    by_company = defaultdict(list)
    no_company = []
    for job in jobs:
        company = (job.get("company") or "").strip()
        if company:
            by_company[normalize_company(company)].append(job)
        else:
            no_company.append(job)

    result = []
    for company_jobs in by_company.values():
        best = min(company_jobs, key=location_rank)
        result.append(best)
    result.extend(no_company)

    dropped = len(jobs) - len(result)
    if dropped:
        print(f"company proximity dedup: kept {len(result)}, dropped {dropped} duplicate company locations")
    return result
