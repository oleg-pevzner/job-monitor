"""Indeed job search via Apify."""

from __future__ import annotations

from job_monitor.sources._apify import (
    ACTORS, run_apify_actor, normalize_url,
    title_matches, company_excluded, clean_location, format_indeed_salary,
)


def search_indeed_jobs(apify_token: str, config: dict) -> list[dict]:
    """Search Indeed via Apify actor."""
    all_jobs, seen_urls = [], set()
    filters = config.get("filters", {})
    keywords = filters.get("title_keywords", config.get("title_keywords", []))
    exclude = filters.get("title_exclude", config.get("title_exclude", []))
    company_excl = filters.get("company_exclude", config.get("company_exclude", []))

    for query in config["search_queries"]:
        for location in config["locations"]:
            print(f"[Indeed] {query} in {location}...")
            items = run_apify_actor(ACTORS["indeed"], {
                "title": query, "location": location, "country": "us",
                "limit": config.get("jobs_per_search", 10), "datePosted": "1",
            }, apify_token)
            print(f"  found {len(items)} jobs")

            for item in items:
                raw_url = item.get("url") or item.get("jobUrl") or ""
                if not raw_url:
                    continue
                job_url = normalize_url(raw_url)
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                title = item.get("title", "")
                if keywords and not title_matches(title, keywords, exclude):
                    continue

                employer = item.get("employer") or {}
                if company_excluded(employer.get("name", ""), company_excl):
                    continue

                salary_info = item.get("baseSalary") or {}
                salary = format_indeed_salary(salary_info)
                loc = item.get("location") or {}

                all_jobs.append({
                    "url": job_url, "title": title,
                    "company": employer.get("name", ""),
                    "company_url": employer.get("companyPageUrl") or employer.get("corporateWebsite") or "",
                    "company_description": (employer.get("briefDescription") or "")[:200],
                    "location": clean_location(loc.get("city", "") if isinstance(loc, dict) else str(loc)),
                    "salary": salary,
                    "seniority": "",
                    "source_query": query,
                })

    return all_jobs
