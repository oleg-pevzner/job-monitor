# job-monitor

Automated job monitoring CLI + MCP server. Searches LinkedIn, Indeed, USAJobs, and Google Jobs via Apify, deduplicates across sources, stores in SQLite, and sends email digests.

## Quick commands

```bash
# Search jobs (requires APIFY_API_TOKEN)
job-monitor search --query "Software Engineer" --location "SF Bay Area" --source linkedin --output json

# Full pipeline with config file
job-monitor run --config config.yml --dry-run
job-monitor run --config config.yml

# Generate a starter config
job-monitor config init --name "My Search"

# Query stored jobs
job-monitor jobs list --db ./jobs.db --since 7d --output json

# Composable pipeline
job-monitor search --config config.yml --output json | job-monitor dedup --db ./jobs.db --output json | job-monitor store --db ./jobs.db
```

## MCP server

Start as MCP server for AI agent integration:
```bash
job-monitor mcp
```

Tools: search_jobs, dedup_jobs, store_jobs, list_jobs, run_monitor, validate_config

## Architecture

- `job_monitor/sources/` - Job board scrapers (linkedin, indeed, usajobs, google_jobs)
- `job_monitor/dedup.py` - 3-layer deduplication (title+company, database, company proximity)
- `job_monitor/storage/` - Storage backends (sqlite default, supabase optional)
- `job_monitor/pipeline.py` - Full pipeline orchestration
- `job_monitor/cli.py` - CLI with argparse subcommands
- `job_monitor/mcp_server.py` - MCP stdio server
- `job_monitor/notify/` - Email notifications via Resend
- `job_monitor/integrations/` - Optional: Google Sheets, DM enrichment, cold emails
