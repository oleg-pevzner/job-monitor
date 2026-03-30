"""USAJobs search via Apify."""

from __future__ import annotations

from job_monitor.sources._apify import (
    ACTORS, run_apify_actor, normalize_url,
    title_matches, clean_location,
)


def search_usajobs(apify_token: str, config: dict) -> list[dict]:
    """Search USAJobs via Apify actor."""
    all_jobs, seen_urls = [], set()
    filters = config.get("filters", {})
    keywords = filters.get("title_keywords", config.get("title_keywords", []))
    exclude = filters.get("title_exclude", config.get("title_exclude", []))

    for query in config["search_queries"]:
        for location in config["locations"]:
            print(f"[USAJobs] {query} in {location}...")
            items = run_apify_actor(ACTORS["usajobs"], {
                "keyword": query, "location": location,
                "daysBack": 7, "maxJobs": config.get("jobs_per_search", 10),
            }, apify_token, wait=180)
            print(f"  found {len(items)} jobs")

            for item in items:
                raw_url = item.get("applyUrl") or item.get("detailUrl") or ""
                if not raw_url:
                    continue
                job_url = normalize_url(raw_url)
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                title = item.get("positionTitle", "")
                if keywords and not title_matches(title, keywords, exclude):
                    continue

                org = item.get("organizationName") or item.get("departmentName") or ""
                all_jobs.append({
                    "url": job_url, "title": title,
                    "company": org,
                    "company_url": "",
                    "company_description": (item.get("departmentName") or "")[:200],
                    "location": clean_location(item.get("locationDisplay", "")),
                    "salary": item.get("salary", ""),
                    "seniority": item.get("pay_scale_grade", ""),
                    "source_query": query,
                })

    return all_jobs
