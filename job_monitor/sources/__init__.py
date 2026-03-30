"""Job source registry and search orchestration."""

from __future__ import annotations

from job_monitor.sources._apify import is_fulltime_salary
from job_monitor.sources.linkedin import search_linkedin_jobs
from job_monitor.sources.indeed import search_indeed_jobs
from job_monitor.sources.usajobs import search_usajobs
from job_monitor.sources.google_jobs import search_google_jobs

SEARCH_FNS = {
    "linkedin": search_linkedin_jobs,
    "indeed": search_indeed_jobs,
    "usajobs": search_usajobs,
    "google_jobs": search_google_jobs,
}

AVAILABLE_SOURCES = list(SEARCH_FNS.keys())


def search_all_sources(apify_token: str, config: dict) -> list[dict]:
    """Search all configured sources and merge results."""
    sources = config.get("sources", ["linkedin"])
    all_jobs = []
    seen_urls = set()

    filters = config.get("filters", {})
    loc_exclude = filters.get("location_exclude", [])
    loc_allow = filters.get("location_allow", [])
    max_annual = filters.get("salary_max_annual", 0)

    for source in sources:
        fn = SEARCH_FNS.get(source)
        if not fn:
            print(f"unknown source: {source}")
            continue
        jobs = fn(apify_token, config)
        for job in jobs:
            if job["url"] in seen_urls:
                continue
            seen_urls.add(job["url"])
            loc_lower = (job.get("location") or "").lower()
            if loc_allow:
                if not any(a in loc_lower for a in loc_allow):
                    continue
            elif loc_exclude:
                if any(ex in loc_lower for ex in loc_exclude):
                    continue
            if max_annual and is_fulltime_salary(job.get("salary", ""), max_annual):
                continue
            all_jobs.append(job)

    print(f"\ntotal unique jobs across {len(sources)} sources: {len(all_jobs)}")
    return all_jobs
