#!/usr/bin/env python3
"""
D2L → Google Calendar sync.
Runs on every wake/login via launchd, but only does real work
the first time each day — subsequent triggers exit immediately.
"""
import asyncio
import fcntl
import sys
from datetime import date
from pathlib import Path

from src.scraper       import scrape_all
from src.parser        import parse_scraped_data
from src.calendar_sync import sync_events
from src.database      import init_db, is_synced, mark_synced

LAST_RUN_FILE = Path(__file__).parent / ".last_run"
LOG_FILE      = Path(__file__).parent / "sync.log"
LOG_MAX_BYTES = 1_000_000  # 1 MB


def _already_ran_today() -> bool:
    try:
        with open(LAST_RUN_FILE, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            content = f.read().strip()
            fcntl.flock(f, fcntl.LOCK_UN)
        return content == str(date.today())
    except FileNotFoundError:
        return False


def _mark_ran_today():
    with open(LAST_RUN_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(str(date.today()))
        fcntl.flock(f, fcntl.LOCK_UN)


def _rotate_log():
    """Truncate sync.log if it exceeds 1 MB to prevent unbounded growth."""
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
        LOG_FILE.write_text("")


def main():
    if _already_ran_today():
        print("Already synced today. Skipping.")
        return

    _rotate_log()

    print("=" * 50)
    print("  D2L → Google Calendar Sync")
    print("=" * 50)

    init_db()

    try:
        raw_data = asyncio.run(scrape_all())
    except Exception as e:
        print(f"\n[ERROR] Scraping failed: {e}")
        print("Check your credentials: python3 migrate_credentials.py")
        sys.exit(1)

    events = parse_scraped_data(raw_data)

    if not events:
        print("\nNo upcoming events found. Nothing to sync.")
    else:
        sync_events(events, is_synced, mark_synced)
        print("\nSync complete!")

    # Mark as done for today regardless (even if nothing new was found)
    _mark_ran_today()


if __name__ == "__main__":
    main()
