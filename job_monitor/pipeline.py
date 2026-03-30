"""Pipeline orchestration: search -> dedup -> enrich -> store -> notify."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from job_monitor.sources import search_all_sources
from job_monitor.dedup import dedup_by_title_company, dedup_against_storage, dedup_by_company_proximity
from job_monitor.storage import create_storage


def run(config: dict, dry_run: bool = False) -> dict:
    """Run the full monitor pipeline.

    Returns a result dict with counts and job list for structured output.
    """
    load_dotenv()

    apify_token = os.environ.get("APIFY_API_TOKEN")
    if not apify_token:
        print("error: APIFY_API_TOKEN environment variable is required")
        print("  get one free at https://console.apify.com/sign-up")
        return {"error": "APIFY_API_TOKEN not set"}

    storage = create_storage(config)
    db_path = config.get("storage", {}).get("path", "./jobs.db")

    # Search
    all_jobs = search_all_sources(apify_token, config)
    all_jobs = dedup_by_title_company(all_jobs)

    # Dedup against stored jobs
    if not dry_run:
        new_jobs = dedup_against_storage(storage, all_jobs)
    else:
        existing_count = storage.count()
        new_jobs = all_jobs
        print(f"dry run: would dedup against {existing_count} existing jobs")

    # Company proximity dedup
    location_priority = config.get("location_priority", [])
    if location_priority:
        new_jobs = dedup_by_company_proximity(new_jobs, location_priority)

    # Enrichment (optional)
    if config.get("enrichment", {}).get("enabled"):
        try:
            from job_monitor.integrations.enrichment import enrich_decision_makers
            enrich_decision_makers(new_jobs, config)

            from job_monitor.integrations.email_drafter import draft_cold_emails
            draft_cold_emails(new_jobs, config)
        except Exception as e:
            print(f"enrichment/drafting failed (non-fatal): {e}")

    # Store
    if not dry_run:
        storage.insert_jobs(new_jobs)

    # Google Sheets (optional)
    spreadsheet_id = None
    if config.get("sheets", {}).get("name") and not dry_run:
        try:
            from job_monitor.integrations.sheets import append_to_sheet
            spreadsheet_id = append_to_sheet(storage, new_jobs, config)
        except Exception as e:
            print(f"Google Sheets sync failed (non-fatal): {e}")

    # Email notification (optional)
    notifications = config.get("notifications", {})
    email_config = notifications.get("email", {})
    emailed = False
    if email_config.get("to") and not dry_run:
        resend_key = os.environ.get("RESEND_API_KEY")
        if resend_key:
            try:
                from job_monitor.notify.email import send_email
                send_email(new_jobs, len(all_jobs), config, spreadsheet_id=spreadsheet_id)
                emailed = True
            except Exception as e:
                print(f"email notification failed (non-fatal): {e}")
        else:
            print("RESEND_API_KEY not set, skipping email notification")

    result = {
        "sources": len(config.get("sources", ["linkedin"])),
        "searched": len(all_jobs),
        "new": len(new_jobs),
        "stored": len(new_jobs) if not dry_run else 0,
        "emailed": emailed,
        "email_to": email_config.get("to", ""),
        "db_path": db_path,
        "dry_run": dry_run,
        "jobs": new_jobs,
    }

    return result
