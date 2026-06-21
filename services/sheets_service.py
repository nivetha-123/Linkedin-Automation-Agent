"""
Thin wrapper around gspread for reading target profiles and writing back
outreach status. No business logic lives here -- this can be swapped for a
CSV-backed implementation in tests (see tests/fixtures/).
"""
from datetime import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_not_exception_type

from config.settings import settings

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

REQUIRED_COLUMNS = settings.yaml_config["sheets"]["required_columns"]


class SheetsService:
    def __init__(self, sheet_id: Optional[str] = None, service_account_path: Optional[str] = None):
        self.sheet_id = sheet_id or settings.google_sheet_id
        self.service_account_path = service_account_path or settings.service_account_path
        self._client = None
        self._worksheet = None

    def _connect(self):
        if self._client is not None and self._worksheet is not None:
            return
        creds = Credentials.from_service_account_file(self.service_account_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        try:
            sheet = client.open_by_key(self.sheet_id)
        except gspread.exceptions.APIError as e:
            raise RuntimeError(
                f"Could not open Google Sheet with ID '{self.sheet_id}'. "
                f"Check that GOOGLE_SHEET_ID in .env is correct and that the sheet is "
                f"shared with your service account email (found in service_account.json "
                f"under 'client_email')."
            ) from e

        worksheet_name = settings.yaml_config["sheets"]["worksheet_name"]
        try:
            worksheet = sheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound as e:
            available = [ws.title for ws in sheet.worksheets()]
            raise RuntimeError(
                f"Could not find a tab named '{worksheet_name}' in your Google Sheet. "
                f"Available tabs: {available}. "
                f"Rename your tab to '{worksheet_name}' or change 'worksheet_name' in "
                f"config/config.yaml to match an existing tab."
            ) from e

        # only commit state once both steps succeed, so a partial failure
        # never leaves _client set but _worksheet still None
        self._client = client
        self._worksheet = worksheet
        self._validate_headers()

    def _validate_headers(self):
        headers = self._worksheet.row_values(1)
        missing = [c for c in REQUIRED_COLUMNS if c not in headers]
        if missing:
            raise ValueError(
                f"Sheet is missing required columns: {missing}. "
                f"Expected: {REQUIRED_COLUMNS}. See linkedin_targets_template.csv"
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(RuntimeError),
        reraise=True,
    )
    def read_pending(self, limit: int) -> list[dict]:
        """Return up to `limit` rows where status is empty or 'pending'."""
        self._connect()
        records = self._worksheet.get_all_records()
        pending = []
        for idx, row in enumerate(records, start=2):  # row 1 is header
            status = (row.get("status") or "").strip().lower()
            if status in ("", "pending"):
                row["_row_index"] = idx
                pending.append(row)
            if len(pending) >= limit:
                break
        logger.info(f"Found {len(pending)} pending profiles in sheet")
        return pending

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def update_row(self, row_index: int, updates: dict):
        """Update specific columns for a given row by header name."""
        self._connect()
        headers = self._worksheet.row_values(1)
        for col_name, value in updates.items():
            if col_name not in headers:
                logger.warning(f"Column '{col_name}' not found in sheet headers, skipping")
                continue
            col_idx = headers.index(col_name) + 1
            self._worksheet.update_cell(row_index, col_idx, value)
        logger.info(f"Updated row {row_index}: {list(updates.keys())}")

    def mark_sent(self, row_index: int, note_used: str):
        self.update_row(row_index, {
            "status": "sent",
            "note_used": note_used,
            "sent_timestamp": datetime.utcnow().isoformat(),
            "followup_due": "",  # computed by scheduler
        })

    def mark_final_status(self, row_index: int, final_status: str):
        self.update_row(row_index, {"final_status": final_status})