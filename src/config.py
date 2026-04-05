import os
from dotenv import load_dotenv

load_dotenv()

D2L_USERNAME = os.getenv("D2L_USERNAME")
D2L_PASSWORD = os.getenv("D2L_PASSWORD")
D2L_BASE_URL = os.getenv("D2L_BASE_URL", "https://pdsb.elearningontario.ca")

GOOGLE_CREDENTIALS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "credentials", "credentials.json"
)
GOOGLE_TOKEN_FILE = os.path.join(
    os.path.dirname(__file__), "..", "credentials", "token.json"
)
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "synced_events.db")

# Validate required credentials at import time so failures are obvious
if not D2L_USERNAME or not D2L_PASSWORD:
    raise EnvironmentError(
        "D2L_USERNAME and D2L_PASSWORD must be set in your .env file.\n"
        f"Copy .env.example to .env and fill in your credentials."
    )
