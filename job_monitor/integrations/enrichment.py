"""Decision-maker enrichment for job postings.

Waterfall enrichment strategy:
1. Apify LinkedIn Company Employees actor (for LinkedIn-sourced jobs)
2. Apify Decision Maker Email Finder (for jobs with a known domain)
3. Prospeo search-person + enrich-person (accept catch-all emails)
4. Prospeo email-finder direct (name + domain -> email)
5. AnyMailFinder fallback

This is an optional advanced feature. Install with: pip install job-monitor[enrichment]
Requires: PROSPEO_API_KEY and/or APIFY_API_TOKEN environment variables.
"""

from __future__ import annotations

import os
import re
import time
import logging
from urllib.parse import urlparse

import requests

from job_monitor.sources._apify import APIFY_BASE_URL, run_apify_actor

logger = logging.getLogger(__name__)

PROSPEO_BASE_URL = "https://api.prospeo.io"
ANYMAILFINDER_URL = "https://api.anymailfinder.com/v5.1/find-email/person"

APIFY_ACTORS = {
    "linkedin_employees": "harvestapi~linkedin-company-employees",
    "dm_email_finder": "snipercoder~decision-maker-email-finder",
}

MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 60


def _is_linkedin_url(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url if "://" in url else f"https://{url}").hostname or ""
    return "linkedin.com" in host.lower()


def _dm_result(name: str, title: str, email: str, email_status: str, source: str) -> dict:
    return {
        "dm_name": name, "dm_title": title, "dm_email": email,
        "dm_email_status": email_status, "dm_source": source,
    }


def _extract_domain_from_url(company_url: str) -> str | None:
    if not company_url:
        return None
    parsed = urlparse(company_url if "://" in company_url else f"https://{company_url}")
    host = (parsed.hostname or "").lower()
    skip_hosts = ("linkedin.com", "indeed.com", "glassdoor.com", "usajobs.gov")
    if host and not any(s in host for s in skip_hosts):
        if host.startswith("www."):
            host = host[4:]
        return host
    return None


def _guess_domain_from_name(company_name: str) -> str | None:
    if not company_name:
        return None
    name = company_name.strip()
    for suffix in [", Inc.", ", Inc", " Inc.", " Inc", " LLC", " Corp.",
                   " Corp", " Ltd.", " Ltd", " Co.", " Co"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    clean = re.sub(r"[^a-z0-9]", "", name.lower())
    if clean and len(clean) > 2:
        return f"{clean}.com"
    return None


def resolve_domain(company_url: str, company_name: str,
                   domain_overrides: dict | None = None) -> str | None:
    domain = _extract_domain_from_url(company_url)
    if domain:
        return domain
    if domain_overrides and company_name:
        override = domain_overrides.get(company_name.lower().strip())
        if override:
            return override
    return _guess_domain_from_name(company_name)


def _rank_by_title(candidates: list[dict], target_titles: list[str]) -> list[dict]:
    def sort_key(candidate: dict) -> int:
        title = (candidate.get("title") or "").lower()
        for rank, target in enumerate(target_titles):
            if target.lower() in title:
                return rank
        return len(target_titles)
    return sorted(candidates, key=sort_key)


def _post_with_retry(url: str, headers: dict, payload: dict, context: str = "") -> requests.Response:
    resp = None
    for attempt in range(MAX_RETRIES):
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        remaining = resp.headers.get("x-minute-request-left")
        if remaining is not None:
            try:
                if int(remaining) < 5:
                    time.sleep(15)
            except ValueError:
                pass
        if resp.status_code != 429:
            return resp
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_WAIT_SECONDS)
    return resp


def _search_dm_via_linkedin_actor(linkedin_url: str, config: dict, apify_token: str) -> dict | None:
    enrichment_config = config.get("enrichment", {})
    seniority_ids = enrichment_config.get("dm_linkedin_seniority_ids", ["210", "220", "300", "310", "320"])
    title_queries = enrichment_config.get("dm_title_queries", [])

    input_json = {
        "companies": [linkedin_url],
        "profileScraperMode": "Full + email search ($12 per 1k)",
        "maxItems": 5,
        "seniorityLevelIds": seniority_ids,
        "companyBatchMode": "all_at_once",
    }
    if title_queries:
        input_json["jobTitles"] = title_queries[:5]

    items = run_apify_actor(APIFY_ACTORS["linkedin_employees"], input_json, apify_token)
    items_with_email = [i for i in items if i.get("email")]
    if not items_with_email:
        return None

    ranked = _rank_by_title(
        [{"title": i.get("headline") or i.get("title") or "",
          "first_name": i.get("firstName", ""), "last_name": i.get("lastName", ""),
          "email": i.get("email", "")} for i in items_with_email],
        title_queries,
    )
    best = ranked[0]
    return _dm_result(
        name=f"{best['first_name']} {best['last_name']}".strip(),
        title=best.get("title", ""), email=best["email"],
        email_status="linkedin_actor", source="apify_linkedin",
    )


def _search_dm_via_apify_dm_finder(domain: str, config: dict, apify_token: str) -> dict | None:
    enrichment_config = config.get("enrichment", {})
    target_titles = enrichment_config.get("dm_title_queries", [])

    input_json = {"domain": domain, "decision_maker_category": "director_head_president", "max_leads_to_find": 3}
    items = run_apify_actor(APIFY_ACTORS["dm_email_finder"], input_json, apify_token)
    candidates_with_email = [i for i in items if i.get("04_Email") or i.get("email")]
    if not candidates_with_email:
        return None

    ranked = _rank_by_title(
        [{"title": i.get("07_Title") or i.get("title") or "",
          "first_name": i.get("02_First_name") or i.get("first_name") or "",
          "last_name": i.get("03_Last_name") or i.get("last_name") or "",
          "email": i.get("04_Email") or i.get("email", "")} for i in candidates_with_email],
        target_titles,
    )
    best = ranked[0]
    return _dm_result(
        name=f"{best['first_name']} {best['last_name']}".strip(),
        title=best.get("title", ""), email=best["email"],
        email_status="apify_dm_finder", source="apify_dm_finder",
    )


def _search_dm_via_prospeo(domain: str, api_key: str, amf_api_key: str | None, config: dict) -> dict | None:
    enrichment_config = config.get("enrichment", {})
    target_titles = enrichment_config.get("dm_title_queries", [])
    seniority_levels = enrichment_config.get("dm_seniority_levels",
                                              ["Director", "Manager", "Head", "Vice President", "C-Suite"])
    headers = {"X-KEY": api_key, "Content-Type": "application/json"}

    for page in (1, 2):
        payload = {"page": page, "filters": {
            "company": {"websites": {"include": [domain]}},
            "person_seniority": {"include": seniority_levels},
        }}
        resp = _post_with_retry(f"{PROSPEO_BASE_URL}/search-person", headers, payload, context=domain)
        if resp.status_code != 200:
            break
        data = resp.json()
        if data.get("error"):
            break
        results_list = data.get("results", [])
        if not isinstance(results_list, list) or not results_list:
            break

        candidates = [{"person_id": item.get("person", {}).get("person_id", ""),
                       "first_name": item.get("person", {}).get("first_name", ""),
                       "last_name": item.get("person", {}).get("last_name", ""),
                       "title": item.get("person", {}).get("current_job_title", "")}
                      for item in results_list]
        candidates = _rank_by_title(candidates, target_titles)

        for candidate in candidates[:6]:
            person_id = candidate.get("person_id", "")
            first_name = candidate.get("first_name", "")
            last_name = candidate.get("last_name", "")
            title = candidate.get("title", "")
            if not person_id and not (first_name and last_name):
                continue

            # Enrich person
            enrich_payload: dict = {"only_verified_email": False}
            if person_id:
                enrich_payload["data"] = {"person_id": person_id}
            else:
                enrich_payload["data"] = {"first_name": first_name, "last_name": last_name, "company_website": domain}

            enrich_resp = _post_with_retry(f"{PROSPEO_BASE_URL}/enrich-person", headers, enrich_payload,
                                           context=f"{first_name} {last_name}")
            if enrich_resp.status_code == 200:
                result = enrich_resp.json()
                if not result.get("error"):
                    person = result.get("person", {})
                    email_obj = person.get("email", {})
                    email = email_obj.get("email", "") if isinstance(email_obj, dict) else (email_obj if isinstance(email_obj, str) else "")
                    if email:
                        email_status = email_obj.get("status", "UNVERIFIED").upper() if isinstance(email_obj, dict) else "UNVERIFIED"
                        return _dm_result(
                            name=f"{person.get('first_name', first_name)} {person.get('last_name', last_name)}".strip(),
                            title=person.get("current_job_title", "") or title,
                            email=email, email_status=email_status, source="prospeo",
                        )

            # Direct email finder fallback
            if first_name and last_name:
                finder_resp = _post_with_retry(
                    f"{PROSPEO_BASE_URL}/email-finder", headers,
                    {"first_name": first_name, "last_name": last_name, "domain": domain},
                    context=f"email-finder:{first_name}@{domain}",
                )
                if finder_resp.status_code == 200:
                    fdata = finder_resp.json()
                    femail = fdata.get("email") or fdata.get("response", {}).get("email", "")
                    if femail and not fdata.get("error"):
                        return _dm_result(name=f"{first_name} {last_name}".strip(), title=title,
                                          email=femail, email_status="prospeo_finder", source="prospeo_email_finder")

            # AnyMailFinder fallback
            if amf_api_key and first_name and last_name:
                try:
                    amf_resp = requests.post(ANYMAILFINDER_URL, json={
                        "first_name": first_name, "last_name": last_name, "domain": domain,
                    }, headers={"Authorization": amf_api_key, "Content-Type": "application/json"}, timeout=30)
                    if amf_resp.status_code == 200:
                        amf_data = amf_resp.json()
                        if amf_data.get("email") and amf_data.get("email_status") in ("valid", "risky"):
                            return _dm_result(name=f"{first_name} {last_name}".strip(), title=title,
                                              email=amf_data["email"], email_status="anymailfinder", source="anymailfinder")
                except Exception:
                    pass

    return None


def _search_dm_for_company(linkedin_url, domain, company_name, apify_token, prospeo_key, amf_key, config) -> dict | None:
    if linkedin_url and apify_token:
        result = _search_dm_via_linkedin_actor(linkedin_url, config, apify_token)
        if result:
            return result
    if domain and apify_token:
        result = _search_dm_via_apify_dm_finder(domain, config, apify_token)
        if result:
            return result
    if domain and prospeo_key:
        result = _search_dm_via_prospeo(domain, prospeo_key, amf_key, config)
        if result:
            return result
    return None


def enrich_decision_makers(jobs: list[dict], config: dict) -> None:
    """Enrich jobs with decision-maker info. Mutates jobs in place."""
    apify_token = os.environ.get("APIFY_API_TOKEN")
    prospeo_key = os.environ.get("PROSPEO_API_KEY")
    amf_key = os.environ.get("ANYMAILFINDER_API_KEY")
    enrichment_config = config.get("enrichment", {})
    domain_overrides = enrichment_config.get("domain_overrides", {})

    if not apify_token and not prospeo_key:
        print("neither APIFY_API_TOKEN nor PROSPEO_API_KEY set, skipping DM enrichment")
        return

    company_groups: dict[str, dict] = {}
    domain_cache: dict[tuple, str | None] = {}

    for job in jobs:
        company_url = job.get("company_url", "")
        company_name = job.get("company", "")
        linkedin_url = company_url if _is_linkedin_url(company_url) else ""

        if linkedin_url:
            key = linkedin_url
            if key not in company_groups:
                domain = domain_overrides.get(company_name.lower().strip()) if domain_overrides else None
                if not domain:
                    domain = _guess_domain_from_name(company_name)
                company_groups[key] = {"jobs": [], "linkedin_url": linkedin_url, "domain": domain, "company_name": company_name}
        else:
            cache_key = (company_url, company_name)
            if cache_key not in domain_cache:
                domain_cache[cache_key] = resolve_domain(company_url, company_name, domain_overrides)
            domain = domain_cache[cache_key]
            if not domain:
                continue
            key = domain
            if key not in company_groups:
                company_groups[key] = {"jobs": [], "linkedin_url": "", "domain": domain, "company_name": company_name}

        company_groups[key]["jobs"].append(job)

    dm_found = 0
    for key, group in company_groups.items():
        try:
            dm = _search_dm_for_company(
                linkedin_url=group["linkedin_url"], domain=group["domain"],
                company_name=group["company_name"], apify_token=apify_token,
                prospeo_key=prospeo_key, amf_key=amf_key, config=config,
            )
            if dm:
                dm_found += 1
                for job in group["jobs"]:
                    job.update(dm)
            time.sleep(1)
        except Exception as e:
            logger.warning("DM enrichment failed for %s: %s", key, e)

    print(f"DM enrichment: {dm_found}/{len(company_groups)} companies matched")
