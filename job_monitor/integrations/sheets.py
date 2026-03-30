"""Google Sheets integration for job monitor.

Appends new job rows to a Google Sheet. Auto-creates the sheet on first run.
Install with: pip install job-monitor[sheets]
"""

from __future__ import annotations

import os
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SHEET_COLUMNS = [
    ("Date Found", "_date"),
    ("Job Title", "title"),
    ("Company", "company"),
    ("Location", "location"),
    ("Salary", "salary"),
    ("Contact Name", "dm_name"),
    ("Contact Title", "dm_title"),
    ("Contact Email", "dm_email"),
    ("Source", "dm_source"),
    ("Cold Email Draft", "cold_email_draft"),
    ("Status", "_status"),
    ("Job URL", "url"),
]


def _setup_auth_from_env() -> None:
    """Write Google OAuth JSON from env vars to temp files (for CI)."""
    token_json = os.environ.get("GOOGLE_TOKEN_JSON", "")
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if token_json and not os.environ.get("GOOGLE_TOKEN_PATH"):
        path = os.path.join(tempfile.gettempdir(), "google_token.json")
        with open(path, "w") as f:
            f.write(token_json)
        os.environ["GOOGLE_TOKEN_PATH"] = path
    if creds_json and not os.environ.get("GOOGLE_CREDENTIALS_PATH"):
        path = os.path.join(tempfile.gettempdir(), "google_credentials.json")
        with open(path, "w") as f:
            f.write(creds_json)
        os.environ["GOOGLE_CREDENTIALS_PATH"] = path


def _get_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    _setup_auth_from_env()
    token_path = os.environ.get("GOOGLE_TOKEN_PATH", "")
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "")
    if not token_path or not creds_path:
        raise ValueError(
            "Google OAuth not configured. Set GOOGLE_TOKEN_PATH + GOOGLE_CREDENTIALS_PATH "
            "env vars, or GOOGLE_TOKEN_JSON + GOOGLE_CREDENTIALS_JSON for CI."
        )

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(f"Credentials not found: {creds_path}")
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())
    return creds


def _get_sheets_service():
    from googleapiclient.discovery import build
    return build("sheets", "v4", credentials=_get_credentials())


def _create_spreadsheet(title: str, sheet_name: str, columns: list[tuple]) -> str:
    service = _get_sheets_service()
    headers = [col[0] for col in columns]
    body = {"properties": {"title": title}, "sheets": [{"properties": {"title": sheet_name}}]}
    spreadsheet = service.spreadsheets().create(body=body).execute()
    spreadsheet_id = spreadsheet["spreadsheetId"]
    sheet_id = spreadsheet["sheets"][0]["properties"]["sheetId"]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1",
        valueInputOption="RAW", body={"values": [headers]},
    ).execute()

    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": [
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                                    "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold"}},
    ]}).execute()
    return spreadsheet_id


def _ensure_tab_exists(spreadsheet_id: str, sheet_name: str, columns: list[tuple]) -> None:
    service = _get_sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if sheet_name in existing_tabs:
        return

    resp = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]}).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]

    headers = [col[0] for col in columns]
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1",
        valueInputOption="RAW", body={"values": [headers]},
    ).execute()

    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": [
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                                    "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold"}},
    ]}).execute()


def append_to_sheet(storage, new_jobs: list[dict], config: dict) -> str | None:
    """Append new jobs to Google Sheet. Returns spreadsheet_id."""
    sheets_config = config.get("sheets", {})
    columns = sheets_config.get("columns", DEFAULT_SHEET_COLUMNS)
    sheet_name = sheets_config.get("name", "Jobs")
    spreadsheet_id = sheets_config.get("spreadsheet_id")

    if not spreadsheet_id:
        # Try to read from a local config file
        config_file = Path(".job-monitor-sheets.json")
        if config_file.exists():
            with open(config_file) as f:
                sheet_config = json.load(f)
                spreadsheet_id = sheet_config.get(sheet_name)

    if not spreadsheet_id:
        spreadsheet_id = _create_spreadsheet(sheet_name, sheet_name, columns)
        config_file = Path(".job-monitor-sheets.json")
        existing = {}
        if config_file.exists():
            with open(config_file) as f:
                existing = json.load(f)
        existing[sheet_name] = spreadsheet_id
        with open(config_file, "w") as f:
            json.dump(existing, f, indent=2)
        print(f"created Google Sheet: {sheet_name} ({spreadsheet_id})")

    if not new_jobs:
        return spreadsheet_id

    _ensure_tab_exists(spreadsheet_id, sheet_name, columns)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = []
    for job in new_jobs:
        row = []
        for _, field in columns:
            if field == "_date":
                row.append(today)
            elif field == "_status":
                row.append("New")
            else:
                row.append(job.get(field, ""))
        rows.append(row)

    service = _get_sheets_service()
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'",
        valueInputOption="RAW", body={"values": rows},
    ).execute()
    print(f"appended {len(rows)} rows to Google Sheet")
    return spreadsheet_id
