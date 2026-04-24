#!/usr/bin/env python3
"""Sync wifi_log.csv rows to Google Sheets (appends new rows only).

Supports two auth modes (set sheets.auth_mode in config.ini):
  service_account  — Google Cloud service account JSON (default)
  oauth            — Personal Google account via OAuth2 (browser consent on first run)
"""

import csv
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def _auth_service_account(creds_path):
    from google.oauth2.service_account import Credentials
    return Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)


def _auth_oauth(creds_path, token_path):
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            # open_browser=True works on desktop; on headless use run_console()
            try:
                creds = flow.run_local_server(port=0, open_browser=True)
            except Exception:
                creds = flow.run_console()
        token_path.write_text(creds.to_json())

    return creds


def sync_to_sheets(cfg, csv_file: Path, state_file: Path, logger):
    import gspread

    base_dir = csv_file.parent.parent
    spreadsheet_id = cfg.get("sheets", "spreadsheet_id", fallback="").strip()
    worksheet_name = cfg.get("sheets", "worksheet_name", fallback="WiFi Log")
    auth_mode = cfg.get("sheets", "auth_mode", fallback="service_account")

    creds_file = cfg.get("sheets", "credentials_file", fallback="credentials.json")
    creds_path = Path(creds_file) if Path(creds_file).is_absolute() else base_dir / creds_file

    if not spreadsheet_id:
        logger.warning("sheets.spreadsheet_id not set in config.ini, skipping sync")
        return
    if not creds_path.exists():
        logger.warning("Credentials file not found: %s", creds_path)
        return

    if auth_mode == "oauth":
        token_path = base_dir / ".oauth_token.json"
        creds = _auth_oauth(creds_path, token_path)
    else:
        creds = _auth_service_account(creds_path)

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=10000, cols=20)

    last_synced = 0
    if state_file.exists():
        try:
            last_synced = int(state_file.read_text().strip())
        except ValueError:
            last_synced = 0

    if not csv_file.exists():
        return

    with open(csv_file, newline="") as f:
        reader = list(csv.reader(f))

    if not reader:
        return

    header = reader[0]
    data_rows = reader[1:]

    new_rows = data_rows[last_synced:]

    # Write header only when sheet is empty
    sheet_rows = ws.get_all_values()
    if not sheet_rows:
        ws.append_row(header, value_input_option="RAW")
        logger.info("Header written to sheet")

    if not new_rows:
        logger.debug("No new rows to sync")
        return

    ws.append_rows(new_rows, value_input_option="RAW")
    last_synced += len(new_rows)
    state_file.write_text(str(last_synced))
    logger.info("Synced %d new rows to Google Sheets (%d total)", len(new_rows), last_synced)


def reset_sheet(cfg, csv_file: Path, state_file: Path, logger):
    """Clear the sheet, reset sync state, and re-sync from scratch."""
    import gspread

    base_dir = csv_file.parent.parent
    spreadsheet_id = cfg.get("sheets", "spreadsheet_id", fallback="").strip()
    worksheet_name = cfg.get("sheets", "worksheet_name", fallback="WiFi Log")
    auth_mode = cfg.get("sheets", "auth_mode", fallback="service_account")

    creds_file = cfg.get("sheets", "credentials_file", fallback="credentials.json")
    creds_path = Path(creds_file) if Path(creds_file).is_absolute() else base_dir / creds_file

    if auth_mode == "oauth":
        creds = _auth_oauth(creds_path, base_dir / ".oauth_token.json")
    else:
        creds = _auth_service_account(creds_path)

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(worksheet_name)
        ws.clear()
        logger.info("Sheet '%s' cleared", worksheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=10000, cols=20)

    # Explicitly write the header right after clearing — don't rely on detection
    if csv_file.exists():
        with open(csv_file, newline="") as f:
            header = next(csv.reader(f), None)
        if header:
            ws.update([header], "A1", value_input_option="RAW")
            logger.info("Header written to sheet")

    if state_file.exists():
        state_file.unlink()
        logger.info("Sync state reset")

    sync_to_sheets(cfg, csv_file, state_file, logger)


if __name__ == "__main__":
    import argparse
    import configparser
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Clear sheet and re-sync from scratch")
    args = parser.parse_args()

    base = Path(__file__).parent
    cfg = configparser.ConfigParser()
    cfg.read(base / "config.ini")

    csv_file = base / "logs" / "wifi_log.csv"
    state_file = base / ".sync_state"

    if args.reset:
        reset_sheet(cfg, csv_file, state_file, logger)
    else:
        sync_to_sheets(cfg, csv_file, state_file, logger)
