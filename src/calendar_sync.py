"""
Google Calendar integration.
First run: opens a browser for one-time OAuth authorization.
Subsequent runs: uses the saved token automatically.
"""
import os
import stat
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from src.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE, GOOGLE_SCOPES

CALENDAR_NAME = "D2L School"


def _get_service():
    """Authenticate and return a Google Calendar API service object."""
    creds = None

    if os.path.exists(GOOGLE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, GOOGLE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Google credentials not found at {GOOGLE_CREDENTIALS_FILE}.\n"
                    "Follow the setup instructions to download credentials.json."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_CREDENTIALS_FILE, GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token — chmod 600 so only the owner can read the refresh token
        with open(GOOGLE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        os.chmod(GOOGLE_TOKEN_FILE, stat.S_IRUSR | stat.S_IWUSR)

    return build("calendar", "v3", credentials=creds)


def _get_or_create_calendar(service) -> str:
    """Return the ID of the 'D2L School' calendar, creating it if needed."""
    page_token = None
    while True:
        result = service.calendarList().list(pageToken=page_token).execute()
        for cal in result.get("items", []):
            if cal.get("summary") == CALENDAR_NAME:
                print(f"[calendar] Using existing '{CALENDAR_NAME}' calendar.")
                return cal["id"]
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    new_cal = service.calendars().insert(body={
        "summary": CALENDAR_NAME,
        "description": "Automatically synced from D2L",
        "timeZone": "America/Toronto",
    }).execute()
    print(f"[calendar] Created new '{CALENDAR_NAME}' calendar.")
    return new_cal["id"]


def sync_events(events: list[tuple[str, dict]], db_is_synced, db_mark_synced):
    """
    Push new events to Google Calendar, skipping already-synced ones.
    events — list of (stable_key, gcal_event_dict)
    """
    service     = _get_service()
    calendar_id = _get_or_create_calendar(service)
    added = skipped = 0

    for d2l_key, event in events:
        if db_is_synced(d2l_key):
            skipped += 1
            continue
        try:
            created = service.events().insert(calendarId=calendar_id, body=event).execute()
            db_mark_synced(d2l_key, created["id"])
            print(f"[calendar] Added: {event['summary']}")
            added += 1
        except HttpError as e:
            print(f"[calendar] Failed to add '{event.get('summary')}': {e}")

    print(f"[calendar] Done — {added} added, {skipped} already synced.")
