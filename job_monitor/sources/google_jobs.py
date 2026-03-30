"""Google Jobs search via Apify."""

from __future__ import annotations

from job_monitor.sources._apify import (
    ACTORS, run_apify_actor, normalize_url,
    title_matches, company_excluded, clean_location,
    best_apply_url, is_recent_posting, format_google_salary,
)


def search_google_jobs(apify_token: str, config: dict) -> list[dict]:
    """Search Google Jobs via Apify actor."""
    all_jobs, seen_urls = [], set()
    filters = config.get("filters", {})
    keywords = filters.get("title_keywords", config.get("title_keywords", []))
    exclude = filters.get("title_exclude", config.get("title_exclude", []))
    company_excl = filters.get("company_exclude", config.get("company_exclude", []))
    max_age = config.get("google_jobs_max_age_days", 14)

    for query in config["search_queries"]:
        for location in config["locations"]:
            print(f"[Google Jobs] {query} in {location}...")
            items = run_apify_actor(ACTORS["google_jobs"], {
                "query": query, "location": location, "country": "us",
                "num_results": config.get("jobs_per_search", 10),
            }, apify_token)
            print(f"  found {len(items)} jobs")

            for item in items:
                apply_opts = item.get("apply_options") or []
                raw_url = best_apply_url(apply_opts) if apply_opts else (item.get("share_link") or "")
                if not raw_url:
                    continue
                job_url = normalize_url(raw_url)
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                title = item.get("title", "")
                if keywords and not title_matches(title, keywords, exclude):
                    continue

                company_name = item.get("company_name", "")
                if company_excluded(company_name, company_excl):
                    continue

                exts = item.get("detected_extensions") or {}
                posted_at = exts.get("posted_at", "")
                if posted_at and not is_recent_posting(posted_at, max_age):
                    continue

                all_jobs.append({
                    "url": job_url, "title": title,
                    "company": company_name,
                    "company_url": "",
                    "company_description": "",
                    "location": clean_location(item.get("location", "")),
                    "salary": format_google_salary(exts.get("salary", "")),
                    "seniority": exts.get("schedule_type", ""),
                    "source_query": query,
                })

    return all_jobs
