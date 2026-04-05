"""
Logs into D2L via Microsoft SSO, then uses D2L's REST API
to pull calendar events, assignment due dates, and quiz dates
across all enrolled courses. No announcements.
"""
import json
import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from src.config import D2L_USERNAME, D2L_PASSWORD, D2L_BASE_URL, D2L_ORG_ID

# Security note: Playwright relies on the system certificate store for TLS
# validation. All D2L calls use HTTPS. Certificate pinning is not supported
# by Playwright — ensure you run this on a trusted network.
API_VER_LP = "1.7"
API_VER_LE = "1.7"

_D2L_HOST = urlparse(D2L_BASE_URL).netloc  # e.g. "pdsb.elearningontario.ca"


def _on_d2l(url: str) -> bool:
    """True if the given URL is on the D2L host (not Microsoft login)."""
    return urlparse(url).netloc == _D2L_HOST


# ──────────────────────────────────────────────────────────────────────────────
# Login
# ──────────────────────────────────────────────────────────────────────────────

async def _login(page):
    """Navigate to D2L and log in via Microsoft SSO."""
    print("[scraper] Navigating to D2L login page...")
    await page.goto(f"{D2L_BASE_URL}/d2l/login", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(4000)

    current_url = page.url
    print(f"[scraper] Landed on: {current_url}")

    if _on_d2l(current_url):
        print("[scraper] Already logged in.")
        return

    # Direct D2L login form
    try:
        await page.wait_for_selector("#userName, #d2l_username, input[name='username']", timeout=4000)
        await page.fill("#userName, #d2l_username, input[name='username']", D2L_USERNAME)
        await page.fill("#password, input[name='password']", D2L_PASSWORD)
        await page.click("button[type='submit'], input[type='submit']")
        await page.wait_for_load_state("networkidle", timeout=30000)
        print("[scraper] Logged in via D2L direct login.")
        return
    except PWTimeout:
        pass

    # Microsoft SSO (PDSB uses this)
    try:
        await page.wait_for_selector("#i0116", timeout=20000)
        await page.wait_for_timeout(800)
        await page.fill("#i0116", D2L_USERNAME)
        await page.wait_for_timeout(800)
        await page.click("#idSIButton9")

        await page.wait_for_selector("#i0118", timeout=20000)
        await page.wait_for_timeout(800)
        await page.fill("#i0118", D2L_PASSWORD)
        await page.wait_for_timeout(800)
        await page.click("#idSIButton9")

        # "Stay signed in?" — click Yes (better for nightly automation)
        try:
            await page.wait_for_selector("#idSIButton9", timeout=8000)
            await page.click("#idSIButton9")
        except PWTimeout:
            pass

        try:
            await page.wait_for_load_state("networkidle", timeout=45000)
        except PWTimeout:
            pass
        await page.wait_for_timeout(3000)

        final_url = page.url
        print(f"[scraper] Post-login URL: {final_url}")

        if _on_d2l(final_url):
            print("[scraper] Logged in via Microsoft SSO.")
            return

        if "microsoftonline" in final_url:
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            if _on_d2l(page.url):
                print("[scraper] Logged in via Microsoft SSO (delayed).")
                return

    except PWTimeout as e:
        print(f"[scraper] Microsoft SSO timed out: {e}")

    raise RuntimeError(
        "[scraper] Could not complete login. "
        "Check your credentials: python3 migrate_credentials.py"
    )


# ──────────────────────────────────────────────────────────────────────────────
# API helper
# ──────────────────────────────────────────────────────────────────────────────

async def _api_get(page, path: str):
    """Authenticated GET using the browser session cookies."""
    url = f"{D2L_BASE_URL}{path}"
    try:
        response = await page.request.get(url, timeout=20000)
        if response.ok:
            return await response.json()
        else:
            print(f"[api] {path} → HTTP {response.status}")
            return None
    except Exception as e:
        print(f"[api] {path} failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Enrolled courses
# ──────────────────────────────────────────────────────────────────────────────

async def _get_courses(page) -> list[dict]:
    """Return active course offerings the user is enrolled in."""
    data = await _api_get(
        page,
        f"/d2l/api/lp/{API_VER_LP}/enrollments/myenrollments/?pageSize=100&isActive=1"
    )
    if not data:
        return []

    courses = []
    for item in data.get("Items", []):
        org = item.get("OrgUnit", {})
        if org.get("Type", {}).get("Code") in ("Course Offering", "Course"):
            courses.append({
                "name": org.get("Name", "Unknown"),
                "org_id": str(org.get("Id", "")),
            })

    print(f"[scraper] Enrolled in {len(courses)} courses: {[c['name'] for c in courses]}")
    return courses


# ──────────────────────────────────────────────────────────────────────────────
# Calendar events
# ──────────────────────────────────────────────────────────────────────────────

async def _get_calendar_events(page, courses: list[dict]) -> list[dict]:
    """
    Fetch upcoming calendar events from D2L.
    Tries the global org first, then falls back to per-course endpoints.
    Calendar events include teacher-created events, test dates, etc.
    """
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=180)
    start_str = now.strftime("%Y-%m-%dT00:00:00.000Z")
    end_str   = end.strftime("%Y-%m-%dT23:59:59.000Z")

    all_events = []
    seen_ids   = set()

    def _parse_events(data, fallback_course="") -> list[dict]:
        items = []
        raw = data if isinstance(data, list) else data.get("Objects", [])
        for ev in raw:
            ev_id = str(ev.get("CalendarEventId") or ev.get("Id") or "")
            title = ev.get("Title", "").strip()
            if not title:
                continue
            items.append({
                "source": "calendar",
                "d2l_id": ev_id,
                "title": title,
                "date_str": ev.get("EndDateTime") or ev.get("StartDateTime", ""),
                "start_str": ev.get("StartDateTime", ""),
                "course": ev.get("OrgUnitName", fallback_course),
                "description": (
                    ev.get("Description", {}).get("Text", "")
                    if isinstance(ev.get("Description"), dict)
                    else str(ev.get("Description", ""))
                ),
            })
        return items

    # 1. Try global org calendar
    data = await _api_get(
        page,
        f"/d2l/api/le/{API_VER_LE}/{D2L_ORG_ID}/calendar/events/upcoming/"
        f"?startDateTime={start_str}&endDateTime={end_str}"
    )
    if data:
        for ev in _parse_events(data):
            if ev["d2l_id"] not in seen_ids:
                seen_ids.add(ev["d2l_id"])
                all_events.append(ev)

    # 2. Per-course calendar (catches events global missed)
    for course in courses:
        data = await _api_get(
            page,
            f"/d2l/api/le/{API_VER_LE}/{course['org_id']}/calendar/events/upcoming/"
            f"?startDateTime={start_str}&endDateTime={end_str}"
        )
        if not data:
            continue
        for ev in _parse_events(data, course["name"]):
            if ev["d2l_id"] not in seen_ids:
                seen_ids.add(ev["d2l_id"])
                all_events.append(ev)

    print(f"[scraper] Found {len(all_events)} calendar events.")
    return all_events


# ──────────────────────────────────────────────────────────────────────────────
# Assignments (due dates)
# ──────────────────────────────────────────────────────────────────────────────

async def _get_assignments(page, courses: list[dict]) -> list[dict]:
    """Fetch assignment folders and their due dates per course."""
    items = []
    seen = set()

    for course in courses:
        data = await _api_get(
            page,
            f"/d2l/api/le/{API_VER_LE}/{course['org_id']}/dropbox/folders/"
        )
        if not data:
            continue

        for folder in (data if isinstance(data, list) else data.get("Objects", [])):
            due = folder.get("DueDate") or folder.get("EndDate", "")
            name = folder.get("Name", "").strip()
            folder_id = str(folder.get("Id", ""))
            if not name or not due:
                continue
            key = f"assign-{folder_id}"
            if key not in seen:
                seen.add(key)
                items.append({
                    "source": "assignment",
                    "d2l_id": folder_id,
                    "title": name,
                    "date_str": due,
                    "start_str": due,
                    "course": course["name"],
                    "description": f"Assignment due — {course['name']}",
                })

    print(f"[scraper] Found {len(items)} assignments with due dates.")
    return items


# ──────────────────────────────────────────────────────────────────────────────
# Quizzes
# ──────────────────────────────────────────────────────────────────────────────

async def _get_quizzes(page, courses: list[dict]) -> list[dict]:
    """Fetch quizzes and their close/end dates per course."""
    items = []
    seen = set()

    for course in courses:
        # Try both API versions — PDSB may only support one
        data = None
        for ver in ["1.7", "1.0"]:
            data = await _api_get(
                page,
                f"/d2l/api/le/{ver}/{course['org_id']}/quizzes/"
            )
            if data:
                break

        if not data:
            continue

        for quiz in (data if isinstance(data, list) else data.get("Objects", [])):
            avail = quiz.get("Availability", {})
            due = (
                quiz.get("EndDate")
                or quiz.get("DueDate")
                or (avail.get("EndDate") if isinstance(avail, dict) else None)
                or ""
            )
            name = quiz.get("Name", "").strip()
            quiz_id = str(quiz.get("QuizId") or quiz.get("Id", ""))
            if not name or not due:
                continue
            key = f"quiz-{quiz_id}"
            if key not in seen:
                seen.add(key)
                items.append({
                    "source": "quiz",
                    "d2l_id": quiz_id,
                    "title": f"Quiz: {name}",
                    "date_str": due,
                    "start_str": due,
                    "course": course["name"],
                    "description": f"Quiz closes — {course['name']}",
                })

    print(f"[scraper] Found {len(items)} quizzes.")
    return items


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

async def scrape_all() -> dict:
    """
    Log in and pull calendar events, assignments, and quizzes from D2L.
    No announcements.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            await _login(page)

            courses     = await _get_courses(page)
            cal_events  = await _get_calendar_events(page, courses)
            assignments = await _get_assignments(page, courses)
            quizzes     = await _get_quizzes(page, courses)
        finally:
            await browser.close()

    return {
        "events":      cal_events,
        "assignments": assignments,
        "quizzes":     quizzes,
    }


if __name__ == "__main__":
    result = asyncio.run(scrape_all())
    print(json.dumps(result, indent=2, default=str))
