"""Browser-only UI contract check with explicit API fixtures, not a backend E2E test."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/api_sentinel/static"
monitors = []
fail_save = False


def route_request(route):
    global fail_save
    request = route.request
    path = urlsplit(request.url).path
    if path.startswith("/api/"):
        if request.headers.get("x-api-key") != "ui-test-key":
            route.fulfill(status=401, json={"error": {"message": "Unauthorized"}})
            return
        if path.endswith("/system"):
            data = {
                "worker_alive": True,
                "pending_alerts": 0,
                "failed_alerts": 0,
                "alert_channel": "console",
            }
        elif path.endswith("/stats"):
            data = {
                "completed_checks": 10,
                "success_rate_percent": 90,
                "latency_p50_ms": 123,
                "open_incidents": 1,
            }
        elif path.endswith("/checks"):
            data = {
                "items": [
                    {
                        "finished_at": "2026-11-13T12:00:00Z",
                        "result": "SUCCESS",
                        "http_status": 200,
                        "latency_ms": 123,
                    }
                ],
                "next_cursor": None,
            }
        elif path.endswith("/incidents"):
            data = {"items": [], "next_cursor": None}
        elif path.endswith(("/pause", "/resume")):
            monitors[0]["status"] = "PAUSED" if path.endswith("/pause") else "UNKNOWN"
            data = monitors[0]
        elif request.method in ("POST", "PATCH"):
            if fail_save:
                route.fulfill(status=503, json={"error": {"message": "Test: database unavailable"}})
                fail_save = False
                return
            values = json.loads(request.post_data)
            values.update(
                id="00000000-0000-0000-0000-000000000001", status="UNKNOWN", last_checked_at=None
            )
            if request.method == "POST":
                monitors.append(values)
            else:
                monitors[0].update(values)
            data = values
        else:
            data = {"items": monitors, "next_cursor": None}
        route.fulfill(json=data)
    else:
        file = STATIC / ("index.html" if path == "/" else path.removeprefix("/static/"))
        mime = {".html": "text/html", ".css": "text/css", ".js": "application/javascript"}
        if file.is_file() and file.parent == STATIC:
            route.fulfill(body=file.read_bytes(), content_type=mime[file.suffix])
        else:
            route.fulfill(status=404)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True, channel=os.getenv("SENTINEL_BROWSER_CHANNEL")
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("http://127.0.0.1:8000/**", route_request)
    page.goto("http://127.0.0.1:8000")
    page.wait_for_load_state("networkidle")
    page.get_by_label("Klucz API").fill("wrong")
    page.get_by_role("button", name="Połącz", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("Nieprawidłowy")
    page.get_by_label("Klucz API").fill("ui-test-key")
    page.get_by_role("button", name="Połącz", exact=True).click()
    expect(page.get_by_text("Pierwszy adres, pierwszy pomiar.")).to_be_visible()
    page.get_by_role("button", name="Dodaj pierwszy monitor").click()
    page.get_by_label("Nazwa", exact=True).fill("Demo API")
    page.get_by_label("Publiczny adres URL").fill("https://example.com")
    fail_save = True
    page.get_by_role("button", name="Zapisz monitor").click()
    expect(page.get_by_role("alert")).to_contain_text("database unavailable")
    expect(page.get_by_label("Nazwa", exact=True)).to_have_value("Demo API")
    page.get_by_role("button", name="Zapisz monitor").click()
    expect(page.get_by_role("dialog")).not_to_be_visible()
    page.get_by_role("button", name="Pauza", exact=True).click()
    expect(page.get_by_text("Wstrzymany", exact=True)).to_be_visible()
    page.get_by_role("button", name="Wznów", exact=True).click()
    page.get_by_role("button", name="Demo API", exact=True).click()
    expect(page.locator("#success-rate")).to_have_text("90%")
    expect(page.locator("#latency")).to_have_text("123 ms")
    screenshots = ROOT / ".local/verification"
    screenshots.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshots / "dashboard-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(screenshots / "dashboard-mobile.png"), full_page=True)
    page.reload()
    expect(page.get_by_role("heading", name="Otwórz swój panel")).to_be_visible()
    assert page.evaluate("localStorage.length === 0 && sessionStorage.length === 0")
    assert not errors, errors
    browser.close()
print(
    "UI smoke passed: auth, empty, failed save, retry, create, pause/resume, history, mobile, lock"
)
