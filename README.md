# job-monitor

Search LinkedIn, Indeed, USAJobs, and Google Jobs from the command line. Deduplicates across sources so you only see new postings. Optionally finds hiring manager emails and drafts personalized outreach for each posting.

Non-interactive, JSON-pipeable, and ships with an [MCP server](#mcp-server) so AI agents can use it too.

## Quick start

```bash
pip install -e .

# Get a free Apify API token at https://console.apify.com/sign-up
export APIFY_API_TOKEN=your_token

# Search
job-monitor search --query "Software Engineer" --location "SF Bay Area" --source linkedin

# Or use a config file
job-monitor config init --name "My Search"
job-monitor run --config config.yml --dry-run
```

### Daily monitoring via GitHub Actions

1. Fork this repo
2. Copy `examples/software-engineer.yml` to `config.yml`, edit your search queries
3. Add `APIFY_API_TOKEN` to repo secrets
4. Optionally add `RESEND_API_KEY` for email notifications ([resend.com](https://resend.com))
5. Push. Runs daily at 7:15 AM Pacific.

## CLI

All commands support `--output json|table|csv|quiet` and `--help` with examples.

```bash
# Full pipeline
job-monitor run --config config.yml
job-monitor run --config config.yml --dry-run

# Search only
job-monitor search --query "Backend Engineer" --location "SF Bay Area" --source linkedin
job-monitor search --config config.yml --output json

# Composable pipes
job-monitor search --config config.yml --output json \
  | job-monitor dedup --db ./jobs.db --output json \
  | job-monitor store --db ./jobs.db

# Config
job-monitor config init --name "ML Search" --source indeed
job-monitor config validate config.yml

# Query stored jobs
job-monitor jobs list --db ./jobs.db --since 7d --output json
```

## MCP server

Also runs as a stdio MCP server, so AI agents (Claude Code, Cursor, etc.) can call it directly.

```bash
# One-command setup for Claude Code
job-monitor install-mcp

# Or start manually
job-monitor mcp
```

Manual setup -- add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "job-monitor": {
      "command": "job-monitor",
      "args": ["mcp"]
    }
  }
}
```

**Tools:** `search_jobs`, `dedup_jobs`, `store_jobs`, `list_jobs`, `run_monitor`, `validate_config`

## Configuration

YAML config. Only `search_queries` and `locations` are required.

```yaml
name: "My Job Search"

sources: [linkedin, indeed]

search_queries:
  - "Software Engineer"
  - "Backend Engineer"

locations:
  - "San Francisco Bay Area"

jobs_per_search: 15

filters:
  title_keywords: [software, backend, fullstack]
  title_exclude: [senior, staff, principal]
  # company_exclude: []
  # location_allow: []
  # salary_max_annual: 50000

storage:
  backend: sqlite  # or supabase
  path: ./jobs.db

notifications:
  email:
    to: you@example.com
    from: jobs@yourdomain.com
    subject_prefix: "SWE"
    accent_color: "#0066cc"
```

See `examples/` for more patterns.

## How it works

```
search_queries x locations x sources
        |
    Apify actors scrape job boards
        |
    normalize URLs, filter by title/company/location/salary
        |
    dedup layer 1: cross-source title+company key matching
        |
    dedup layer 2: check against SQLite database
        |
    dedup layer 3: one job per company per location
        |
    store new jobs, send email digest
```

## Optional features

**Email digests** -- HTML emails via [Resend](https://resend.com). Configure under `notifications.email` in your config.

**Google Sheets** -- Auto-sync new jobs to a spreadsheet. `pip install job-monitor[sheets]`

**Decision-maker enrichment** -- Find hiring manager contacts via Prospeo/AnyMailFinder and draft cold emails via Claude. `pip install job-monitor[enrichment]`

```yaml
enrichment:
  enabled: true
  dm_title_queries: ["Engineering Manager", "VP of Engineering"]
  resume_context: |
    3 years as a backend engineer. Python, Go, PostgreSQL.
  signer_name: "Alex"
```

Requires `PROSPEO_API_KEY`. Optional: `ANYMAILFINDER_API_KEY`, `ANTHROPIC_API_KEY`.

## Cost

GitHub Actions is free for public repos. Apify's free tier covers light usage (~$0.10/day for a typical search). Resend's free tier covers 100 emails/day. SQLite is a local file.

## License

MIT
