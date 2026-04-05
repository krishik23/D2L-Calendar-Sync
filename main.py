#!/usr/bin/env python3
"""
D2L → Google Calendar sync.
Runs on every wake/login via launchd, but only does real work
the first time each day — subsequent triggers exit immediately.
"""
import asyncio
import sys
from datetime import date
from pathlib import Path

from src.scraper       import scrape_all
from src.parser        import parse_scraped_data
from src.calendar_sync import sync_events
from src.database      import init_db, is_synced, mark_synced

LAST_RUN_FILE = Path(__file__).parent / ".last_run"


def _already_ran_today() -> bool:
    try:
        return LAST_RUN_FILE.read_text().strip() == str(date.today())
    except FileNotFoundError:
        return False


def _mark_ran_today():
    LAST_RUN_FILE.write_text(str(date.today()))


def main():
    if _already_ran_today():
        print("Already synced today. Skipping.")
        return

    print("=" * 50)
    print("  D2L → Google Calendar Sync")
    print("=" * 50)

    init_db()

    try:
        raw_data = asyncio.run(scrape_all())
    except Exception as e:
        print(f"\n[ERROR] Scraping failed: {e}")
        print("Check your D2L credentials in the .env file.")
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
