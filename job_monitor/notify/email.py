"""HTML email digest via Resend."""

from __future__ import annotations

import os
from datetime import datetime, timezone


def send_email(new_jobs: list[dict], total_results: int, config: dict,
               spreadsheet_id: str | None = None):
    """Send HTML digest email via Resend. Skip if no new jobs."""
    try:
        import resend
    except ImportError:
        raise ImportError(
            "Email notifications require the resend package. "
            "Install with: pip install job-monitor[email]"
        )

    if not new_jobs:
        print("no new jobs, skipping email")
        return

    notifications = config.get("notifications", {})
    email_config = notifications.get("email", {})

    email_to = email_config.get("to", "")
    email_from = email_config.get("from", "jobs@example.com")
    prefix = email_config.get("subject_prefix", "Jobs")
    accent = email_config.get("accent_color", "#0066cc")
    email_cc = email_config.get("cc", [])
    link_to_sheet = email_config.get("link_to_sheet", False)

    today = datetime.now(timezone.utc).strftime("%B %-d")
    subject = f"{len(new_jobs)} New {prefix} Job{'s' if len(new_jobs) != 1 else ''} - {today}"
    sources = config.get("sources", ["linkedin"])
    source_label = ", ".join(s.replace("_", " ").title() for s in sources)

    show_cards = not link_to_sheet or not spreadsheet_id

    if spreadsheet_id and not show_cards:
        dm_count = sum(1 for j in new_jobs if j.get("dm_email"))
        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        html = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;color:#333;">
            <h2 style="margin-bottom:16px;">{subject}</h2>
            <p style="font-size:15px;line-height:1.5;">
                New jobs have been added to your tracker{f', {dm_count} with contact info' if dm_count else ''}.
            </p>
            <div style="margin:20px 0;">
                <a href="{sheet_url}" style="display:inline-block;background:{accent};color:#fff;
                   padding:10px 24px;border-radius:6px;text-decoration:none;font-size:15px;font-weight:500;">
                    Open Google Sheet &rarr;
                </a>
            </div>
            <div style="color:#999;font-size:12px;margin-top:24px;padding-top:12px;border-top:1px solid #eee;">
                Searched {source_label} &middot; {total_results} results &middot; {len(new_jobs)} new
            </div>
        </div>
        """
    else:
        sheet_banner = ""
        if spreadsheet_id:
            sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
            sheet_banner = f"""
            <div style="background:#f8f8f8;border-radius:8px;padding:12px 16px;margin-bottom:20px;">
                <span style="font-size:14px;">These jobs have also been added to the
                <a href="{sheet_url}" style="color:{accent};font-weight:500;">tracking sheet</a>.</span>
            </div>
            """

        cards_html = ""
        for job in new_jobs:
            tags = []
            if job.get("location"):
                tags.append(job["location"])
            if job.get("seniority"):
                tags.append(job["seniority"])
            if job.get("salary"):
                tags.append(f"<strong>{job['salary']}</strong>")

            tags_html = " ".join(
                f'<span style="display:inline-block;background:#f0f0f0;color:#555;'
                f'font-size:12px;padding:2px 8px;border-radius:4px;margin-right:4px;">'
                f'{tag}</span>'
                for tag in tags
            )

            company_name = job.get("company", "")
            company_url = job.get("company_url", "")
            if company_url:
                company_html = f'<a href="{company_url}" style="color:#333;text-decoration:none;font-weight:500;">{company_name}</a>'
            else:
                company_html = f'<span style="font-weight:500;">{company_name}</span>'

            company_desc = job.get("company_description", "")
            desc_html = f'<div style="color:#666;font-size:13px;margin-top:4px;">{company_desc}</div>' if company_desc else ""

            cards_html += f"""
            <div style="border-left:3px solid {accent};padding:12px 16px;margin-bottom:16px;">
                <div style="font-size:16px;font-weight:600;">{job['title']}</div>
                <div style="font-size:14px;margin-top:2px;">{company_html}</div>
                {desc_html}
                <div style="margin-top:6px;">{tags_html}</div>
                <div style="margin-top:8px;">
                    <a href="{job['url']}" style="color:{accent};font-size:13px;text-decoration:none;">View posting &rarr;</a>
                </div>
            </div>
            """

        html = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto;color:#333;">
            <h2 style="margin-bottom:20px;">{subject}</h2>
            {sheet_banner}
            {cards_html}
            <div style="color:#999;font-size:12px;margin-top:24px;padding-top:12px;border-top:1px solid #eee;">
                Searched {source_label} &middot; {total_results} results &middot; {len(new_jobs)} new
            </div>
        </div>
        """

    resend.api_key = os.environ["RESEND_API_KEY"]
    email_params = {
        "from": email_from,
        "to": [email_to],
        "subject": subject,
        "html": html,
    }
    if email_cc:
        email_params["cc"] = email_cc if isinstance(email_cc, list) else [email_cc]
    resend.Emails.send(email_params)
    print(f"email sent: {subject}")
