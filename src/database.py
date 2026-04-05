"""
Tracks which events have already been added to Google Calendar
so we never create duplicates.

Security note: This database stores only deduplication keys (D2L entity IDs
and Google Calendar event IDs). No credentials, personal data, or event
content is persisted here — encryption is not warranted.
"""
import sqlite3
from src.config import DB_PATH


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS synced_events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                d2l_key       TEXT UNIQUE,
                gcal_event_id TEXT,
                synced_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def is_synced(d2l_key: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM synced_events WHERE d2l_key = ?", (d2l_key,)
        ).fetchone()
    return row is not None


def mark_synced(d2l_key: str, gcal_event_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO synced_events (d2l_key, gcal_event_id) VALUES (?, ?)",
            (d2l_key, gcal_event_id),
        )
