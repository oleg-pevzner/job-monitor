"""YAML config loading, validation, and defaults."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


REQUIRED_FIELDS = ["search_queries", "locations"]

DEFAULTS = {
    "sources": ["linkedin"],
    "jobs_per_search": 10,
    "google_jobs_max_age_days": 14,
    "storage": {"backend": "sqlite", "path": "./jobs.db"},
    "filters": {
        "title_keywords": [],
        "title_exclude": [],
        "company_exclude": [],
        "location_allow": [],
        "location_exclude": [],
        "salary_max_annual": None,
    },
}


def load_config(path: str) -> dict:
    """Load and validate a YAML config file.

    Returns the merged config with defaults applied.
    """
    config_path = Path(path)
    if not config_path.exists():
        _fail(f"config file not found: {path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        _fail(f"config must be a YAML mapping, got {type(raw).__name__}")

    errors = []
    for field in REQUIRED_FIELDS:
        if field not in raw:
            errors.append(f"missing required field: {field}")
        elif not isinstance(raw[field], list) or not raw[field]:
            errors.append(f"{field} must be a non-empty list")

    if errors:
        _fail(
            "config validation failed:\n"
            + "\n".join(f"  - {e}" for e in errors)
            + f"\n\ncheck your config file: {path}"
        )

    return _merge_defaults(raw)


def merge_cli_overrides(config: dict, **overrides) -> dict:
    """Merge CLI flag overrides into a config dict.

    CLI flags take precedence over config file values.
    """
    for key, value in overrides.items():
        if value is None:
            continue
        if key in ("query", "queries"):
            config["search_queries"] = value if isinstance(value, list) else [value]
        elif key == "location":
            config["locations"] = value if isinstance(value, list) else [value]
        elif key == "source":
            config["sources"] = value if isinstance(value, list) else [value]
        elif key == "jobs_per_search":
            config["jobs_per_search"] = value
        elif key == "title_keyword":
            config.setdefault("filters", {})["title_keywords"] = value
        elif key == "title_exclude":
            config.setdefault("filters", {})["title_exclude"] = value
        elif key == "db":
            config.setdefault("storage", {})["path"] = value
    return config


def build_config_from_flags(**flags) -> dict:
    """Build a minimal config dict from CLI flags (no config file)."""
    config = {
        "search_queries": flags.get("query", []),
        "locations": flags.get("location", []),
        "sources": flags.get("source") or ["linkedin"],
        "jobs_per_search": flags.get("jobs_per_search", 10),
        "filters": {
            "title_keywords": flags.get("title_keyword", []),
            "title_exclude": flags.get("title_exclude", []),
            "company_exclude": [],
            "location_allow": [],
            "location_exclude": [],
            "salary_max_annual": None,
        },
        "storage": {
            "backend": "sqlite",
            "path": flags.get("db", "./jobs.db"),
        },
    }
    return _merge_defaults(config)


def generate_starter_config(name: str = "My Job Search", source: str = "linkedin",
                            location: str = "San Francisco Bay Area") -> str:
    """Generate a starter YAML config string."""
    return f"""# {name}
# Docs: https://github.com/oleg-pevzner/job-monitor

name: "{name}"

sources:
  - {source}

search_queries:
  - "Software Engineer"
  - "Backend Engineer"

locations:
  - "{location}"

jobs_per_search: 10

filters:
  title_keywords:
    - software
    - backend
    - engineer
  title_exclude:
    - senior
    - staff
    - principal
    - director
  # company_exclude: []
  # location_allow: []
  # salary_max_annual: 50000

storage:
  backend: sqlite
  path: ./jobs.db

# Uncomment to enable email notifications (requires RESEND_API_KEY)
# notifications:
#   email:
#     to: you@example.com
#     from: jobs@yourdomain.com
#     subject_prefix: "SWE"
#     accent_color: "#0066cc"

# Uncomment to enable Google Sheets sync
# sheets:
#   name: "Job Tracker"

# Uncomment for decision-maker enrichment (requires PROSPEO_API_KEY)
# enrichment:
#   enabled: false
#   dm_title_queries: ["Engineering Manager", "VP of Engineering"]
#   resume_context: "Your background here..."
#   signer_name: "Your Name"
"""


def _merge_defaults(config: dict) -> dict:
    """Apply defaults for missing optional fields."""
    for key, default in DEFAULTS.items():
        if key not in config:
            config[key] = default
        elif isinstance(default, dict) and isinstance(config.get(key), dict):
            for k, v in default.items():
                config[key].setdefault(k, v)
    return config


def _fail(message: str):
    """Print error and exit."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)
