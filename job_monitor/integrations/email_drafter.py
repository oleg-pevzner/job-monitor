"""Cold email drafting via Claude API.

For each job with a decision-maker contact, generates a short personalized
cold email. Install with: pip install job-monitor[enrichment]
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """\
You're helping someone write a short, genuine cold email to a person at a company \
that's hiring for a role they're interested in. They already applied online and want \
to reach out directly.

{resume_context}

The email should feel like one real person writing to another.

Rules:
- 2-3 sentences max for the body. Shorter is better.
- Mention that they applied for the role online already.
- Pick ONE specific thing about the role or company to mention, don't be generic.
- No buzzwords, no "I'm confident I'd be a great fit", no "leverage my skills".
- Don't start with "I hope this email finds you well" or "I came across your posting".
- Just be direct and human. It's okay to be casual.
- End with a CTA on its own line, separated by a blank line from the body. Ask for a \
brief call. Keep it casual and specific.
- Never use em dashes or en dashes. Use commas, periods, or "and" instead.
- Return ONLY the email body (the middle part). No greeting, no signature."""

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def draft_cold_emails(jobs: list[dict], config: dict) -> None:
    """Draft cold emails for jobs that have DM info. Mutates jobs in place."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set, skipping cold email drafts")
        return

    try:
        import anthropic
    except ImportError:
        print("anthropic package not installed, skipping cold email drafts")
        print("  pip install job-monitor[enrichment]")
        return

    enrichment_config = config.get("enrichment", {})
    model = enrichment_config.get("model", DEFAULT_MODEL)
    resume_context = enrichment_config.get("resume_context", "")
    signer_name = enrichment_config.get("signer_name", "")

    system_prompt = DEFAULT_SYSTEM_PROMPT.format(
        resume_context=f"About the sender:\n{resume_context}" if resume_context else ""
    )

    client = anthropic.Anthropic(api_key=api_key)
    drafted = 0

    for job in jobs:
        dm_name = job.get("dm_name")
        dm_email = job.get("dm_email")
        if not dm_name or not dm_email:
            continue

        user_message = (
            f"Job: {job.get('title', '')} at {job.get('company', '')}\n"
            f"Location: {job.get('location', '')}\n"
            f"Hiring manager: {dm_name}, {job.get('dm_title', '')}"
        )

        try:
            response = client.messages.create(
                model=model, max_tokens=500, system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            body = response.content[0].text if response.content else ""
            if body:
                first_name = dm_name.split()[0] if dm_name else "there"
                sign_off = f"\n\nBest,\n{signer_name}" if signer_name else ""
                job["cold_email_draft"] = f"Hi {first_name},\n\n{body.strip()}{sign_off}"
                drafted += 1
        except Exception as e:
            logger.warning("Cold email draft failed for %s: %s", job.get("company"), e)

    print(f"cold emails drafted: {drafted}")
