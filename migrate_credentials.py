#!/usr/bin/env python3
"""
One-time migration: move D2L credentials from .env into macOS Keychain.

Run this once after pulling the latest code:
    python3 migrate_credentials.py

After a successful migration, .env is deleted and subsequent runs of
main.py read credentials exclusively from the Keychain.
"""
import sys
import getpass
from pathlib import Path

try:
    import keyring
except ImportError:
    print("[migrate] ERROR: 'keyring' package not installed.")
    print("  Run: pip install keyring")
    sys.exit(1)

KEYRING_SERVICE = "d2l-calendar-sync"
KEYS = {
    "d2l_username": "D2L username (e.g. 864343@pdsb.net)",
    "d2l_password": "D2L password",
    "d2l_base_url": "D2L base URL (press Enter for https://pdsb.elearningontario.ca)",
    "d2l_org_id":   "D2L root org ID (press Enter for 8340)",
}
DEFAULTS = {
    "d2l_base_url": "https://pdsb.elearningontario.ca",
    "d2l_org_id":   "8340",
}

ENV_FILE = Path(__file__).parent / ".env"


def _store(key: str, value: str):
    keyring.set_password(KEYRING_SERVICE, key, value)


def _verify(key: str, expected: str) -> bool:
    return keyring.get_password(KEYRING_SERVICE, key) == expected


def _migrate_from_env() -> dict:
    """Read credentials from .env using dotenv (if available)."""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    vals = dotenv_values(ENV_FILE)
    return {
        "d2l_username": vals.get("D2L_USERNAME", ""),
        "d2l_password": vals.get("D2L_PASSWORD", ""),
        "d2l_base_url": vals.get("D2L_BASE_URL", DEFAULTS["d2l_base_url"]),
        "d2l_org_id":   vals.get("D2L_ORG_ID", DEFAULTS["d2l_org_id"]),
    }


def _prompt_credentials() -> dict:
    """Interactively ask for each credential."""
    print("\nEnter your credentials (they will be stored in macOS Keychain):\n")
    creds = {}
    for key, prompt in KEYS.items():
        default = DEFAULTS.get(key)
        if key == "d2l_password":
            val = getpass.getpass(f"  {prompt}: ")
        else:
            val = input(f"  {prompt}: ").strip()
        if not val and default:
            val = default
        creds[key] = val
    return creds


def main():
    print("=" * 54)
    print("  D2L Calendar Sync — Credential Migration")
    print("=" * 54)

    # Check if creds already in keychain
    existing_user = keyring.get_password(KEYRING_SERVICE, "d2l_username")
    if existing_user:
        print(f"\n[migrate] Credentials already in Keychain (username: {existing_user}).")
        overwrite = input("  Overwrite? (y/N): ").strip().lower()
        if overwrite != "y":
            print("[migrate] Nothing changed.")
            return

    # Try reading from .env first
    creds = {}
    if ENV_FILE.exists():
        print(f"\n[migrate] Found .env — reading credentials...")
        creds = _migrate_from_env()
        if creds.get("d2l_username") and creds.get("d2l_password"):
            print(f"  Username : {creds['d2l_username']}")
            print(f"  Base URL : {creds['d2l_base_url']}")
            print(f"  Org ID   : {creds['d2l_org_id']}")
        else:
            print("  .env exists but credentials are incomplete — prompting instead.")
            creds = _prompt_credentials()
    else:
        creds = _prompt_credentials()

    # Validate required fields
    if not creds.get("d2l_username") or not creds.get("d2l_password"):
        print("\n[migrate] ERROR: Username and password are required.")
        sys.exit(1)

    # Store in Keychain
    print("\n[migrate] Storing credentials in macOS Keychain...")
    for key, value in creds.items():
        _store(key, value)

    # Verify round-trip
    for key, value in creds.items():
        if not _verify(key, value):
            print(f"[migrate] ERROR: Verification failed for '{key}'. Keychain write may have failed.")
            sys.exit(1)

    print("[migrate] Verification passed — all credentials confirmed in Keychain.")

    # Delete .env if it exists
    if ENV_FILE.exists():
        ENV_FILE.unlink()
        print(f"[migrate] Deleted {ENV_FILE} (credentials are now in Keychain only).")

    print("\n[migrate] Done. You can verify with:")
    print(f"  security find-generic-password -s '{KEYRING_SERVICE}' -a 'd2l_username' -w")


if __name__ == "__main__":
    main()
