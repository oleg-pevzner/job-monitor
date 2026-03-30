"""LinkedIn job search via Apify."""

from __future__ import annotations

from urllib.parse import quote_plus

from job_monitor.sources._apify import (
    ACTORS, run_apify_actor, normalize_url,
    title_matches, company_excluded, clean_location,
)


def search_linkedin_jobs(apify_token: str, config: dict) -> list[dict]:
    """Search LinkedIn via Apify actor."""
    all_jobs, seen_urls = [], set()
    filters = config.get("filters", {})
    keywords = filters.get("title_keywords", config.get("title_keywords", []))
    exclude = filters.get("title_exclude", config.get("title_exclude", []))
    company_excl = filters.get("company_exclude", config.get("company_exclude", []))

    for query in config["search_queries"]:
        for location in config["locations"]:
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={quote_plus(query)}&location={quote_plus(location)}&f_TPR=r86400"
            )
            print(f"[LinkedIn] {query} in {location}...")
            items = run_apify_actor(
                ACTORS["linkedin"],
                {"urls": [url], "count": config.get("jobs_per_search", 10), "scrapeCompany": True},
                apify_token,
            )
            print(f"  found {len(items)} jobs")

            for item in items:
                raw_url = item.get("link") or item.get("applyUrl") or ""
                if not raw_url:
                    continue
                job_url = normalize_url(raw_url)
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                title = item.get("title", "")
                if keywords and not title_matches(title, keywords, exclude):
                    continue

                company_name = item.get("companyName", "")
                if company_excluded(company_name, company_excl):
                    continue

                company_desc = item.get("companyDescription") or item.get("companySlogan") or ""
                all_jobs.append({
                    "url": job_url, "title": title,
                    "company": company_name,
                    "company_url": item.get("companyLinkedinUrl", ""),
                    "company_description": company_desc[:200] if company_desc else "",
                    "location": clean_location(item.get("location", "")),
                    "salary": item.get("salary", ""),
                    "seniority": item.get("seniorityLevel", ""),
                    "source_query": query,
                })

    return all_jobs
