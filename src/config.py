import os
import keyring

_SERVICE = "d2l-calendar-sync"

D2L_USERNAME = keyring.get_password(_SERVICE, "d2l_username")
D2L_PASSWORD = keyring.get_password(_SERVICE, "d2l_password")
D2L_BASE_URL = (
    keyring.get_password(_SERVICE, "d2l_base_url")
    or os.environ.get("D2L_BASE_URL", "https://pdsb.elearningontario.ca")
)
# Org ID is stored in Keychain so it doesn't appear in the public repo.
# Falls back to the known PDSB root org unit if not explicitly set.
D2L_ORG_ID = keyring.get_password(_SERVICE, "d2l_org_id") or "8340"

GOOGLE_CREDENTIALS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "credentials", "credentials.json"
)
GOOGLE_TOKEN_FILE = os.path.join(
    os.path.dirname(__file__), "..", "credentials", "token.json"
)
# Full calendar scope is required: the app creates a dedicated "D2L School"
# calendar on first run via calendars().insert() and calendarList().list().
# The narrower calendar.events scope does not cover calendar management.
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "synced_events.db")

if not D2L_USERNAME or not D2L_PASSWORD:
    raise EnvironmentError(
        "D2L credentials not found in macOS Keychain.\n"
        "Run: python3 migrate_credentials.py"
    )
