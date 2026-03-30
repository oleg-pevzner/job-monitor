"""Apify actor runner and URL normalization utilities."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

import requests

APIFY_BASE_URL = "https://api.apify.com/v2"

# Aggregator sites that frequently break or redirect; skip in Google Jobs apply_options
BLOCKED_APPLY_DOMAINS = {
    "jobleads.com", "learn4good.com", "jobisjob.com", "jobrapido.com",
    "talent.com", "adzuna.com", "neuvoo.com", "careerjet.com",
}

ACTORS = {
    "linkedin": "curious_coder~linkedin-jobs-scraper",
    "indeed": "valig~indeed-jobs-scraper",
    "usajobs": "shahidirfan~USA-Jobs-Scraper",
    "google_jobs": "johnvc~Google-Jobs-Scraper",
}


def normalize_url(url: str) -> str:
    """Strip tracking params from URLs to get a stable key for dedup.

    Preserves essential query params for sites that use them as identifiers
    (e.g. Indeed's ?jk= parameter).
    """
    parsed = urlparse(url)
    if "indeed.com" in (parsed.netloc or ""):
        from urllib.parse import parse_qs, urlencode
        essential = {k: v for k, v in parse_qs(parsed.query).items() if k in ("jk", "vjk")}
        return urlunparse(parsed._replace(query=urlencode(essential, doseq=True), fragment=""))
    return urlunparse(parsed._replace(query="", fragment=""))


def run_apify_actor(actor: str, input_json: dict, apify_token: str, wait: int = 120) -> list[dict]:
    """Run an Apify actor and return dataset items."""
    headers = {"Authorization": f"Bearer {apify_token}", "Content-Type": "application/json"}
    resp = requests.post(
        f"{APIFY_BASE_URL}/acts/{actor}/runs",
        headers=headers,
        params={"waitForFinish": wait},
        json=input_json,
        timeout=wait + 10,
    )
    if resp.status_code != 201:
        print(f"  Apify run failed ({resp.status_code}): {resp.text[:200]}")
        return []

    dataset_id = resp.json().get("data", {}).get("defaultDatasetId")
    if not dataset_id:
        print("  No dataset returned")
        return []

    items_resp = requests.get(
        f"{APIFY_BASE_URL}/datasets/{dataset_id}/items",
        headers=headers,
        params={"format": "json"},
        timeout=30,
    )
    if items_resp.status_code != 200:
        print(f"  Failed to fetch dataset ({items_resp.status_code})")
        return []

    return items_resp.json()


def clean_location(loc: str) -> str:
    """Strip state abbreviation, country, and zip from location string."""
    if not loc:
        return ""
    # Strip US state abbreviations + zip codes + country
    loc = re.sub(
        r',\s*([A-Z]{2})\s*(\d{5}(-\d{4})?)?$', '', loc
    )
    loc = re.sub(
        r',\s*(United States|USA|US)$', '', loc, flags=re.IGNORECASE
    )
    return loc.strip().rstrip(",")


def title_matches(title: str, keywords: list[str], exclude: list[str] | None = None) -> bool:
    """Check if a job title matches keyword filters."""
    title_lower = title.lower()
    if exclude and any(kw in title_lower for kw in exclude):
        return False
    return any(kw in title_lower for kw in keywords)


def company_excluded(company: str, exclude: list[str] | None = None) -> bool:
    """Check if a company is in the exclusion list."""
    if not exclude or not company:
        return False
    company_lower = company.lower()
    return any(kw in company_lower for kw in exclude)


def best_apply_url(apply_options: list[dict]) -> str:
    """Pick the first apply link that isn't from a blocked aggregator domain."""
    for opt in apply_options:
        link = opt.get("link", "")
        domain = urlparse(link).netloc.lower().lstrip("www.")
        if not any(domain == blocked or domain.endswith("." + blocked)
                   for blocked in BLOCKED_APPLY_DOMAINS):
            return link
    return apply_options[0].get("link", "") if apply_options else ""


def is_recent_posting(posted_at: str, max_days: int = 14) -> bool:
    """Return True if posted_at string indicates a posting within max_days."""
    if not posted_at:
        return True
    s = posted_at.lower().strip()
    if s in ("today", "just posted", "just now"):
        return True
    m = re.search(r'(\d+)\s*(day|hour|minute|week|month|year)', s)
    if not m:
        return True
    num, unit = int(m.group(1)), m.group(2)
    approx_days = {
        "minute": 0, "hour": 0, "day": num,
        "week": num * 7, "month": num * 30, "year": num * 365,
    }.get(unit, 0)
    return approx_days <= max_days


def is_fulltime_salary(salary: str, max_annual: int) -> bool:
    """Return True if salary looks like a full-time annual salary at or above max_annual."""
    if not salary:
        return False
    s = salary.lower()
    if "/yr" not in s and "a year" not in s and "per year" not in s:
        return False
    for m in re.finditer(r'\$([\d,]+)(k)?', s, re.IGNORECASE):
        amount = int(m.group(1).replace(',', ''))
        if m.group(2):
            amount *= 1000
        if amount >= max_annual:
            return True
    return False


def format_indeed_salary(salary_info: dict) -> str:
    """Format Indeed's structured salary data into a readable string."""
    mn, mx = salary_info.get("min"), salary_info.get("max")
    if not mn and not mx:
        return ""
    unit = (salary_info.get("unitOfWork") or "").lower()
    unit_short = {"hour": "hr", "year": "yr", "month": "mo", "week": "wk"}.get(unit, unit)
    parts = []
    if mn:
        parts.append(f"${mn:,.0f}")
    if mx and mx != mn:
        parts.append(f"${mx:,.0f}")
    result = " - ".join(parts)
    if unit_short:
        result += f"/{unit_short}"
    return result


def format_google_salary(raw: str) -> str:
    """Normalize Google Jobs salary strings like '20 an hour' -> '$20/hr'."""
    if not raw:
        return ""
    if "$" in raw:
        return raw
    s = raw.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r'(\d[\d,.]*)', lambda m: f"${m.group(1)}", s)
    s = s.replace(" an hour", "/hr").replace(" a year", "/yr")
    s = s.replace(" a month", "/mo")
    return s
