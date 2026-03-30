# job-monitor

Automated job monitoring across LinkedIn, Indeed, USAJobs, and Google Jobs. Get daily email digests of only new postings. Runs free on GitHub Actions.

**Built for AI agents.** Every command is non-interactive, composable via JSON pipes, and includes `--help` with examples. Ships with a built-in [MCP server](#mcp-server) so Claude Code, Cursor, and other agents can use it as a tool.

## Why?

Job boards show you the same results every day. This tool remembers what you've already seen and only shows you what's new. It searches 4 job boards simultaneously and deduplicates across all of them with 3 layers of matching.

## Quick start

### Try it locally (5 minutes)

```bash
# Install
pip install -e .

# Get a free Apify API token at https://console.apify.com/sign-up
export APIFY_API_TOKEN=your_token

# Search for jobs
job-monitor search --query "Software Engineer" --location "SF Bay Area" --source linkedin

# Or use a config file
job-monitor config init --name "My Search"
job-monitor run --config config.yml --dry-run
```

### Set up daily monitoring (10 minutes)

1. Fork this repo
2. Copy `examples/software-engineer.yml` to `config.yml` and edit your search queries
3. Add `APIFY_API_TOKEN` to your repo's GitHub Actions secrets
4. Add `RESEND_API_KEY` for email notifications (optional, [get one free](https://resend.com))
5. Push. The monitor runs daily at 7:15 AM Pacific via GitHub Actions

## Features

- **4 job boards**: LinkedIn, Indeed, USAJobs, Google Jobs
- **3-layer dedup**: Cross-source title+company matching, database memory, company proximity filtering
- **SQLite storage**: Zero config. Works out of the box, no database setup
- **Email digests**: HTML emails with job cards via [Resend](https://resend.com)
- **Google Sheets**: Auto-sync new jobs to a tracking spreadsheet
- **Decision-maker enrichment**: Find hiring manager contacts (advanced, optional)
- **Cold email drafts**: AI-generated outreach emails via Claude (advanced, optional)
- **MCP server**: Built-in [Model Context Protocol](https://modelcontextprotocol.io) server for AI agents
- **Composable CLI**: Pipe `search | dedup | store | notify` independently
- **GitHub Actions**: Free daily cron with included workflow template

## CLI reference

Every command supports `--output json|table|csv|quiet` and `--help` with examples.

### run

Run the full pipeline: search, dedup, store, notify.

```bash
job-monitor run --config config.yml
job-monitor run --config config.yml --dry-run
job-monitor run --config config.yml --output json
```

### search

Search job boards and output results.

```bash
job-monitor search --config config.yml
job-monitor search --query "Backend Engineer" --location "SF Bay Area" --source linkedin
job-monitor search --query "ML Engineer" --location "NYC" --source linkedin --source indeed --output json
```

### dedup, store, notify

Composable pipeline commands. Each reads JSON from stdin.

```bash
# Chain them together
job-monitor search --config config.yml --output json \
  | job-monitor dedup --db ./jobs.db --output json \
  | job-monitor store --db ./jobs.db

# Notify from stored results
job-monitor jobs list --db ./jobs.db --since 1d --output json \
  | job-monitor notify --to me@example.com --subject-prefix "SWE"
```

### config

```bash
job-monitor config init                                    # generate starter config
job-monitor config init --name "ML Search" --source indeed # with options
job-monitor config validate config.yml                     # check for errors
```

### jobs

```bash
job-monitor jobs list --db ./jobs.db                      # all stored jobs
job-monitor jobs list --db ./jobs.db --since 7d           # last 7 days
job-monitor jobs list --db ./jobs.db --status new --output json
```

## MCP server

job-monitor includes a built-in MCP server for AI agent integration.

### Setup for Claude Code

```bash
job-monitor install-mcp
```

This adds job-monitor to your Claude Code MCP configuration. After restarting Claude Code, you can ask it things like "search for ML engineer jobs in NYC" and it will call job-monitor directly.

### Manual setup

Add to `~/.claude/settings.json`:

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

### Available MCP tools

| Tool | Description |
|------|-------------|
| `search_jobs` | Search job boards with queries, locations, and filters |
| `dedup_jobs` | Filter out previously seen jobs against the database |
| `store_jobs` | Save jobs to SQLite |
| `list_jobs` | Query stored jobs with optional filters |
| `run_monitor` | Run the full pipeline from a config file |
| `validate_config` | Check a config file for errors |

## Configuration

YAML config file with sensible defaults. Only `search_queries` and `locations` are required.

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

See `examples/` for more config patterns.

## How it works

```
search_queries x locations x sources
        |
    [Apify actors scrape job boards]
        |
    normalize URLs + filter by title/company/location/salary
        |
    dedup layer 1: cross-source title+company key matching
        |
    dedup layer 2: check against SQLite/Supabase database
        |
    dedup layer 3: company proximity (one job per company per location)
        |
    (optional) enrich with decision-maker contacts
        |
    store new jobs + send email digest
```

## Advanced: Decision-maker enrichment

Find hiring manager contacts for each job posting. Requires additional API keys.

```yaml
enrichment:
  enabled: true
  dm_title_queries: ["Engineering Manager", "VP of Engineering"]
  dm_seniority_levels: ["Director", "Manager", "Head"]
  resume_context: |
    About me:
    - 3 years as a backend engineer
    - Skills: Python, Go, PostgreSQL
  signer_name: "Alex"
```

Required env vars: `PROSPEO_API_KEY` and/or `APIFY_API_TOKEN`. Optional: `ANYMAILFINDER_API_KEY`, `ANTHROPIC_API_KEY` (for cold email drafts).

## Cost

- **GitHub Actions**: Free for public repos
- **Apify**: Free tier includes ~$5/month of credits. A typical daily search (2 queries x 2 locations x 1 source) costs ~$0.10/day
- **Resend**: Free tier includes 100 emails/day
- **SQLite**: Free (local file, no service needed)
- **Supabase**: Free tier available if you want cloud storage

## License

MIT
