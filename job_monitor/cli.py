"""Agent-friendly CLI for job-monitor.

Every command is non-interactive, supports --output json/table/csv,
and includes examples in --help. Designed for both humans and AI agents.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Custom help formatter that appends examples
# ---------------------------------------------------------------------------

class ExampleHelpFormatter(argparse.RawDescriptionHelpFormatter):
    pass


def _add_output_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output", "-o",
        choices=["json", "table", "csv", "quiet"],
        default=None,
        help="output format (default: table for TTY, json when piped)",
    )


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_run(args):
    """Run the full monitor pipeline."""
    from job_monitor.config import load_config, merge_cli_overrides
    from job_monitor.pipeline import run
    from job_monitor.output import detect_format, format_result

    config = load_config(args.config)
    if args.location:
        merge_cli_overrides(config, location=args.location)

    result = run(config, dry_run=args.dry_run)

    fmt = detect_format(args.output)
    print(format_result(result, fmt))


def cmd_search(args):
    """Search job boards and output results."""
    import os
    from dotenv import load_dotenv
    from job_monitor.output import detect_format, format_jobs

    load_dotenv()
    apify_token = os.environ.get("APIFY_API_TOKEN")
    if not apify_token:
        _error(
            "APIFY_API_TOKEN environment variable is required",
            "  export APIFY_API_TOKEN=your_token",
            "  get one free at https://console.apify.com/sign-up",
        )

    if args.config:
        from job_monitor.config import load_config, merge_cli_overrides
        config = load_config(args.config)
        overrides = {}
        if args.query:
            overrides["query"] = args.query
        if args.location:
            overrides["location"] = args.location
        if args.source:
            overrides["source"] = args.source
        if overrides:
            merge_cli_overrides(config, **overrides)
    elif args.query:
        from job_monitor.config import build_config_from_flags
        config = build_config_from_flags(
            query=args.query,
            location=args.location or ["United States"],
            source=args.source,
            jobs_per_search=args.jobs_per_search,
            title_keyword=args.title_keyword,
            title_exclude=args.title_exclude,
        )
    else:
        _error(
            "--query is required when not using --config",
            '  job-monitor search --query "Software Engineer" --location "SF Bay Area" --source linkedin',
            "  job-monitor search --config config.yml",
        )

    from job_monitor.sources import search_all_sources
    from job_monitor.dedup import dedup_by_title_company
    jobs = search_all_sources(apify_token, config)
    jobs = dedup_by_title_company(jobs)

    fmt = detect_format(args.output)
    print(format_jobs(jobs, fmt))


def cmd_dedup(args):
    """Filter out previously seen jobs."""
    from job_monitor.output import detect_format, format_jobs
    from job_monitor.storage.sqlite import SQLiteStorage
    from job_monitor.dedup import dedup_by_title_company, dedup_against_storage

    jobs = _read_jobs_stdin()
    jobs = dedup_by_title_company(jobs)

    storage = SQLiteStorage(args.db)
    new_jobs = dedup_against_storage(storage, jobs)

    fmt = detect_format(args.output)
    print(format_jobs(new_jobs, fmt))


def cmd_store(args):
    """Save jobs to the database."""
    from job_monitor.storage.sqlite import SQLiteStorage

    jobs = _read_jobs_stdin()
    storage = SQLiteStorage(args.db)
    storage.insert_jobs(jobs)

    result = {"stored": len(jobs), "db_path": args.db}
    if args.output == "json":
        print(json.dumps(result))
    else:
        print(f"stored {len(jobs)} jobs in {args.db}")


def cmd_notify(args):
    """Send email digest of jobs."""
    import os
    from dotenv import load_dotenv
    load_dotenv()

    if not os.environ.get("RESEND_API_KEY"):
        _error(
            "RESEND_API_KEY environment variable is required",
            "  export RESEND_API_KEY=your_key",
            "  get one at https://resend.com",
        )

    jobs = _read_jobs_stdin()
    if not jobs:
        print("no jobs to notify about")
        return

    if args.config:
        from job_monitor.config import load_config
        config = load_config(args.config)
    else:
        if not args.to:
            _error(
                "--to is required when not using --config",
                '  job-monitor notify --to you@example.com --subject-prefix "SWE" < jobs.json',
                "  job-monitor notify --config config.yml < jobs.json",
            )
        config = {
            "notifications": {
                "email": {
                    "to": args.to,
                    "from": args.from_addr or "jobs@example.com",
                    "subject_prefix": args.subject_prefix or "Jobs",
                    "accent_color": "#0066cc",
                }
            },
            "sources": ["linkedin"],
        }

    from job_monitor.notify.email import send_email
    send_email(jobs, len(jobs), config)


def cmd_config_init(args):
    """Generate a starter config file."""
    from job_monitor.config import generate_starter_config

    content = generate_starter_config(
        name=args.name or "My Job Search",
        source=args.source or "linkedin",
        location=args.location or "San Francisco Bay Area",
    )

    output_path = args.output_file or "config.yml"
    if Path(output_path).exists() and not args.force:
        _error(
            f"{output_path} already exists",
            f"  job-monitor config init --force  # overwrite existing file",
            f"  job-monitor config init --output other.yml",
        )

    with open(output_path, "w") as f:
        f.write(content)
    print(f"created {output_path}")


def cmd_config_validate(args):
    """Validate a config file."""
    from job_monitor.config import load_config

    config = load_config(args.config)
    result = {
        "valid": True,
        "sources": config.get("sources", []),
        "queries": len(config.get("search_queries", [])),
        "locations": len(config.get("locations", [])),
    }
    if args.output == "json":
        print(json.dumps(result))
    else:
        print(f"valid config: {result['queries']} queries, {result['locations']} locations, sources: {', '.join(result['sources'])}")


def cmd_jobs_list(args):
    """Query stored jobs."""
    from job_monitor.storage.sqlite import SQLiteStorage
    from job_monitor.output import detect_format, format_jobs

    storage = SQLiteStorage(args.db)
    since = None
    if args.since:
        since = _parse_duration(args.since)
    jobs = storage.list_jobs(since_days=since, status=args.status)

    fmt = detect_format(args.output)
    print(format_jobs(jobs, fmt))


def cmd_mcp(args):
    """Start the MCP stdio server."""
    try:
        from job_monitor.mcp_server import serve
    except ImportError:
        _error(
            "MCP server requires the mcp package",
            "  pip install job-monitor[mcp]",
        )
    serve()


def cmd_install_mcp(args):
    """Add job-monitor to Claude Code MCP config."""
    import shutil

    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        with open(settings_path) as f:
            settings = json.load(f)
    else:
        settings = {}

    job_monitor_bin = shutil.which("job-monitor")
    if not job_monitor_bin:
        job_monitor_bin = "job-monitor"

    servers = settings.setdefault("mcpServers", {})
    servers["job-monitor"] = {
        "command": job_monitor_bin,
        "args": ["mcp"],
    }

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    print(f"added job-monitor MCP server to {settings_path}")
    print("restart Claude Code to activate")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_jobs_stdin() -> list[dict]:
    """Read JSON job array from stdin."""
    if sys.stdin.isatty():
        _error(
            "expected JSON input on stdin",
            "  job-monitor search --config config.yml --output json | job-monitor dedup --db ./jobs.db",
            '  cat jobs.json | job-monitor store --db ./jobs.db',
        )
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        _error(f"invalid JSON on stdin: {e}")
    if not isinstance(data, list):
        _error("expected a JSON array of job objects on stdin")
    return data


def _parse_duration(s: str) -> int:
    """Parse a duration string like '7d', '2w', '30d' into days."""
    s = s.strip().lower()
    if s.endswith("d"):
        return int(s[:-1])
    if s.endswith("w"):
        return int(s[:-1]) * 7
    try:
        return int(s)
    except ValueError:
        _error(f"invalid duration: {s} (use 7d, 2w, or a number of days)")


def _error(*lines: str):
    """Print error message and exit."""
    print(f"error: {lines[0]}", file=sys.stderr)
    for line in lines[1:]:
        print(line, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Parser setup
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-monitor",
        description="Automated job monitoring across LinkedIn, Indeed, USAJobs, and Google Jobs.",
        epilog="""examples:
  job-monitor run --config config.yml
  job-monitor run --config config.yml --dry-run
  job-monitor search --query "Software Engineer" --location "SF Bay Area" --source linkedin
  job-monitor config init --name "My Search"
  job-monitor mcp""",
        formatter_class=ExampleHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    subparsers = parser.add_subparsers(dest="command", help="available commands")

    # --- run ---
    p_run = subparsers.add_parser(
        "run",
        help="run the full monitor pipeline (search + dedup + store + notify)",
        epilog="""examples:
  job-monitor run --config config.yml
  job-monitor run --config config.yml --dry-run
  job-monitor run --config config.yml --output json""",
        formatter_class=ExampleHelpFormatter,
    )
    p_run.add_argument("--config", required=True, help="YAML config file")
    p_run.add_argument("--dry-run", action="store_true", help="preview what would happen without making changes")
    p_run.add_argument("--location", action="append", help="override location (repeatable)")
    _add_output_arg(p_run)
    p_run.set_defaults(func=cmd_run)

    # --- search ---
    p_search = subparsers.add_parser(
        "search",
        help="search job boards and output results",
        epilog="""examples:
  job-monitor search --config config.yml
  job-monitor search --query "Backend Engineer" --location "SF Bay Area" --source linkedin
  job-monitor search --query "ML Engineer" --location "NYC" --source linkedin --source indeed
  job-monitor search --config config.yml --output json | jq '.[] | .title'""",
        formatter_class=ExampleHelpFormatter,
    )
    p_search.add_argument("--config", help="YAML config file")
    p_search.add_argument("--query", action="append", help="job search query (repeatable)")
    p_search.add_argument("--location", action="append", help="location to search (repeatable)")
    p_search.add_argument("--source", action="append", choices=["linkedin", "indeed", "usajobs", "google_jobs"],
                          help="job board (repeatable, default: linkedin)")
    p_search.add_argument("--jobs-per-search", type=int, default=10, help="results per query/location combo (default: 10)")
    p_search.add_argument("--title-keyword", action="append", help="required keyword in job title (repeatable)")
    p_search.add_argument("--title-exclude", action="append", help="exclude jobs with this in title (repeatable)")
    _add_output_arg(p_search)
    p_search.set_defaults(func=cmd_search)

    # --- dedup ---
    p_dedup = subparsers.add_parser(
        "dedup",
        help="filter out previously seen jobs (reads JSON from stdin)",
        epilog="""examples:
  job-monitor search --config config.yml --output json | job-monitor dedup --db ./jobs.db
  job-monitor search --config config.yml --output json | job-monitor dedup --db ./jobs.db --output json""",
        formatter_class=ExampleHelpFormatter,
    )
    p_dedup.add_argument("--db", default="./jobs.db", help="SQLite database path (default: ./jobs.db)")
    _add_output_arg(p_dedup)
    p_dedup.set_defaults(func=cmd_dedup)

    # --- store ---
    p_store = subparsers.add_parser(
        "store",
        help="save jobs to the database (reads JSON from stdin)",
        epilog="""examples:
  job-monitor search --config config.yml --output json | job-monitor store --db ./jobs.db
  cat jobs.json | job-monitor store --db ./jobs.db""",
        formatter_class=ExampleHelpFormatter,
    )
    p_store.add_argument("--db", default="./jobs.db", help="SQLite database path (default: ./jobs.db)")
    _add_output_arg(p_store)
    p_store.set_defaults(func=cmd_store)

    # --- notify ---
    p_notify = subparsers.add_parser(
        "notify",
        help="send email digest of jobs (reads JSON from stdin)",
        epilog="""examples:
  job-monitor search --config config.yml --output json | job-monitor notify --config config.yml
  cat jobs.json | job-monitor notify --to me@example.com --subject-prefix "SWE" """,
        formatter_class=ExampleHelpFormatter,
    )
    p_notify.add_argument("--config", help="YAML config file with notification settings")
    p_notify.add_argument("--to", help="recipient email address")
    p_notify.add_argument("--from-addr", help="sender email address")
    p_notify.add_argument("--subject-prefix", help="email subject prefix")
    _add_output_arg(p_notify)
    p_notify.set_defaults(func=cmd_notify)

    # --- config ---
    p_config = subparsers.add_parser("config", help="create and validate config files")
    config_sub = p_config.add_subparsers(dest="config_command")

    p_config_init = config_sub.add_parser(
        "init",
        help="generate a starter config file",
        epilog="""examples:
  job-monitor config init
  job-monitor config init --name "ML Engineer Search" --source indeed --location "New York"
  job-monitor config init --output my-search.yml""",
        formatter_class=ExampleHelpFormatter,
    )
    p_config_init.add_argument("--name", help="name for your job search")
    p_config_init.add_argument("--source", help="default job board source")
    p_config_init.add_argument("--location", help="default search location")
    p_config_init.add_argument("--output-file", help="output file path (default: config.yml)")
    p_config_init.add_argument("--force", action="store_true", help="overwrite existing file")
    p_config_init.set_defaults(func=cmd_config_init)

    p_config_validate = config_sub.add_parser(
        "validate",
        help="check a config file for errors",
        epilog="""examples:
  job-monitor config validate config.yml""",
        formatter_class=ExampleHelpFormatter,
    )
    p_config_validate.add_argument("config", help="path to YAML config file")
    _add_output_arg(p_config_validate)
    p_config_validate.set_defaults(func=cmd_config_validate)

    # --- jobs ---
    p_jobs = subparsers.add_parser("jobs", help="query stored jobs")
    jobs_sub = p_jobs.add_subparsers(dest="jobs_command")

    p_jobs_list = jobs_sub.add_parser(
        "list",
        help="list stored jobs",
        epilog="""examples:
  job-monitor jobs list --db ./jobs.db
  job-monitor jobs list --db ./jobs.db --since 7d --output json
  job-monitor jobs list --db ./jobs.db --status new --output csv""",
        formatter_class=ExampleHelpFormatter,
    )
    p_jobs_list.add_argument("--db", default="./jobs.db", help="SQLite database path (default: ./jobs.db)")
    p_jobs_list.add_argument("--since", help="only jobs from last N days (e.g. 7d, 2w)")
    p_jobs_list.add_argument("--status", help="filter by status (e.g. new)")
    _add_output_arg(p_jobs_list)
    p_jobs_list.set_defaults(func=cmd_jobs_list)

    # --- mcp ---
    p_mcp = subparsers.add_parser(
        "mcp",
        help="start the MCP stdio server for AI agents",
        epilog="""examples:
  job-monitor mcp
  # Add to Claude Code: job-monitor install-mcp""",
        formatter_class=ExampleHelpFormatter,
    )
    p_mcp.set_defaults(func=cmd_mcp)

    # --- install-mcp ---
    p_install_mcp = subparsers.add_parser(
        "install-mcp",
        help="add job-monitor to Claude Code MCP configuration",
        epilog="""examples:
  job-monitor install-mcp""",
        formatter_class=ExampleHelpFormatter,
    )
    p_install_mcp.set_defaults(func=cmd_install_mcp)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)
