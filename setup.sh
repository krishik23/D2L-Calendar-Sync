#!/bin/bash
# ──────────────────────────────────────────────────────────────────
# D2L Calendar Sync — One-time setup script
# Run this once: bash setup.sh
# ──────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.d2l.calendar.sync"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "================================================"
echo "  D2L → Google Calendar Sync Setup"
echo "================================================"

# ── 1. Python environment ─────────────────────────────────────────
echo ""
echo "Step 1: Setting up Python environment..."
cd "$SCRIPT_DIR"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
playwright install chromium
echo "✓ Python dependencies installed."

# ── 2. Store credentials in macOS Keychain ────────────────────────
echo ""
echo "Step 2: Setting up your credentials (stored in macOS Keychain)..."
echo ""
source .venv/bin/activate
python3 migrate_credentials.py
if [ $? -ne 0 ]; then
    echo "  ✗ Credential setup failed. Aborting."
    exit 1
fi

# ── 3. Google credentials check ───────────────────────────────────
echo ""
echo "Step 3: Checking Google credentials..."

if [ ! -f "$SCRIPT_DIR/credentials/credentials.json" ]; then
    echo ""
    echo "  ✗ credentials/credentials.json not found."
    echo ""
    echo "  You need to set up Google Calendar API access."
    echo "  Follow these steps:"
    echo ""
    echo "  1. Go to: https://console.cloud.google.com/"
    echo "  2. Click 'Select a project' → 'New Project'"
    echo "     Name it: D2L Calendar Sync → click Create"
    echo "  3. In the search bar type 'Google Calendar API' → Enable it"
    echo "  4. Go to 'APIs & Services' → 'OAuth consent screen'"
    echo "     - Choose 'External' → Fill in App name (e.g. D2L Sync)"
    echo "     - Add your Gmail as a test user → Save"
    echo "  5. Go to 'Credentials' → 'Create Credentials' → 'OAuth client ID'"
    echo "     - Application type: Desktop app → Name it → Create"
    echo "  6. Click the download button (⬇) next to your new credential"
    echo "  7. Save the downloaded file as:"
    echo "     $SCRIPT_DIR/credentials/credentials.json"
    echo ""
    read -p "  Press Enter after saving credentials.json to continue..."
else
    echo "✓ credentials.json found."
fi

# ── 4. First run (triggers Google OAuth in browser) ───────────────
echo ""
echo "Step 4: First sync (will open browser for Google login)..."
echo "  A browser window will open asking you to sign in to Google."
echo "  This only happens ONCE. After this it runs silently."
echo ""
read -p "  Run the first sync now? (Y/n): " CONFIRM
CONFIRM="${CONFIRM:-Y}"
if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
    source .venv/bin/activate
    python3 main.py
else
    echo "  Skipped. Run manually whenever you're ready: python3 main.py"
fi

# ── 5. Schedule nightly cron via launchd ──────────────────────────
echo ""
echo "Step 5: Scheduling nightly sync at 11:00 PM..."

PYTHON_PATH="$SCRIPT_DIR/.venv/bin/python3"
LOG_PATH="$SCRIPT_DIR/sync.log"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$SCRIPT_DIR/main.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_PATH</string>
    <key>StandardErrorPath</key>
    <string>$LOG_PATH</string>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>$HOME</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

# Load the launch agent
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo ""
echo "================================================"
echo "  ✓ Setup complete!"
echo ""
echo "  Your D2L events will sync to Google Calendar"
echo "  every night at 11:00 PM automatically."
echo ""
echo "  To run manually anytime:"
echo "    cd '$SCRIPT_DIR'"
echo "    source .venv/bin/activate"
echo "    python3 main.py"
echo ""
echo "  To check logs:"
echo "    cat '$SCRIPT_DIR/sync.log'"
echo ""
echo "  To stop the nightly sync:"
echo "    launchctl unload '$PLIST_PATH'"
echo "================================================"
