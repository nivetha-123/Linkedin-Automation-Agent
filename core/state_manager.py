"""
Local SQLite state tracking. This is the source of truth for the pipeline --
Google Sheets is a synced view of it, so the pipeline can resume correctly
even if it crashes mid-run.

States: pending -> drafted -> sent -> accepted | withdrawn | expired
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from config.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_url TEXT UNIQUE NOT NULL,
    sheet_row_index INTEGER,
    name TEXT,
    headline TEXT,
    note_used TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    sent_timestamp TEXT,
    followup_due TEXT,
    final_status TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_status ON outreach(status);
CREATE INDEX IF NOT EXISTS idx_followup_due ON outreach(followup_due);
"""


class StateManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.state_db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def upsert_pending(self, profile_url: str, sheet_row_index: int, name: str = "", headline: str = ""):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO outreach (profile_url, sheet_row_index, name, headline)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(profile_url) DO UPDATE SET
                     sheet_row_index=excluded.sheet_row_index,
                     name=excluded.name,
                     headline=excluded.headline,
                     updated_at=datetime('now')""",
                (profile_url, sheet_row_index, name, headline),
            )

    def mark_sent(self, profile_url: str, note_used: str):
        sent_at = datetime.utcnow()
        followup_due = sent_at + timedelta(days=settings.followup_days)
        with self._conn() as conn:
            conn.execute(
                """UPDATE outreach
                   SET status='sent', note_used=?, sent_timestamp=?, followup_due=?, updated_at=datetime('now')
                   WHERE profile_url=?""",
                (note_used, sent_at.isoformat(), followup_due.isoformat(), profile_url),
            )
        logger.info(f"Marked sent: {profile_url} (follow-up due {followup_due.date()})")

    def mark_final(self, profile_url: str, final_status: str):
        assert final_status in ("accepted", "withdrawn", "expired")
        with self._conn() as conn:
            conn.execute(
                """UPDATE outreach SET final_status=?, status=?, updated_at=datetime('now')
                   WHERE profile_url=?""",
                (final_status, final_status, profile_url),
            )

    def get_overdue_followups(self) -> list[sqlite3.Row]:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM outreach
                   WHERE status='sent' AND followup_due <= ? AND final_status IS NULL""",
                (now,),
            ).fetchall()
        return rows

    def get_row(self, profile_url: str):
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM outreach WHERE profile_url=?", (profile_url,)
            ).fetchone()
