"""
Converts raw D2L data into Google Calendar events.
No announcement parsing — only structured API data (assignments, quizzes, calendar events).
"""
import hashlib
import dateparser
from datetime import datetime, timedelta, timezone


DATEPARSER_SETTINGS = {
    "RETURN_AS_TIMEZONE_AWARE": True,
    "TIMEZONE": "America/Toronto",
}


def _parse_date(text: str) -> datetime | None:
    if not text:
        return None
    return dateparser.parse(text, settings=DATEPARSER_SETTINGS)


def _stable_key(item: dict) -> str:
    """
    Stable deduplication key across runs.
    Uses the D2L item ID when available (most stable).
    Falls back to a hash of source + title + date.
    """
    d2l_id = str(item.get("d2l_id", "")).strip()
    source = item.get("source", "")
    # Check explicitly for non-empty string (not just truthy, so "0" is valid)
    if d2l_id != "":
        return f"{source}-{d2l_id}"
    dt = _parse_date(item.get("date_str", ""))
    date_part = dt.strftime("%Y-%m-%d") if dt else item.get("date_str", "")[:10]
    raw = f"{source}|{item.get('title', '')}|{date_part}|{item.get('course', '')}"
    return hashlib.md5(raw.encode()).hexdigest()


def _build_gcal_event(item: dict, dt: datetime) -> dict:
    """Build a Google Calendar API event body from a D2L item."""
    title  = item["title"].strip()
    course = item.get("course", "").strip()
    desc   = item.get("description", "").strip()
    summary = f"{title} — {course}" if course and course not in title else title

    # Check raw date string for a time component rather than guessing from midnight
    has_time = "T" in item.get("date_str", "")

    if has_time:
        start = {"dateTime": dt.isoformat(), "timeZone": "America/Toronto"}
        end   = {"dateTime": (dt + timedelta(hours=1)).isoformat(), "timeZone": "America/Toronto"}
    else:
        date_str = dt.strftime("%Y-%m-%d")
        start = {"date": date_str}
        end   = {"date": (dt + timedelta(days=1)).strftime("%Y-%m-%d")}

    return {
        "summary": summary,
        "description": desc or f"From D2L ({item.get('source', 'event')})",
        "start": start,
        "end": end,
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 24 * 60},  # 1 day before
                {"method": "popup", "minutes": 60},        # 1 hour before
            ],
        },
    }


def parse_scraped_data(data: dict) -> list[tuple[str, dict]]:
    """
    Convert raw scraped data into (stable_key, gcal_event) pairs.
    Skips items with no parseable date or events more than 1 day in the past.
    """
    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=1)

    all_items = (
        data.get("events", [])
        + data.get("assignments", [])
        + data.get("quizzes", [])
    )

    output: list[tuple[str, dict]] = []
    skipped_past = 0

    for item in all_items:
        dt = _parse_date(item.get("date_str", ""))
        if not dt:
            continue
        if dt < cutoff:
            skipped_past += 1
            continue
        output.append((_stable_key(item), _build_gcal_event(item, dt)))

    if skipped_past:
        print(f"[parser] Skipped {skipped_past} past events.")
    print(f"[parser] {len(output)} events ready to sync.")
    return output
