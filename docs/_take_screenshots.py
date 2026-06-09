"""Take screenshots of the WoL-Monkey UI for documentation."""

from __future__ import annotations

import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765"
OUT = Path(__file__).parent / "screenshots"
OUT.mkdir(exist_ok=True)

# ── helpers ────────────────────────────────────────────────────────────────


def api(method: str, path: str, **kwargs):
    return requests.request(method, f"{BASE}/api{path}", **kwargs)


def setup_app() -> tuple[str, requests.Session]:
    """Bootstrap the app via API (idempotent). Return (csrf_token, session)."""
    status = api("GET", "/setup/status").json()
    if not status.get("is_complete"):
        api("POST", "/setup/admin", json={"username": "admin", "password": "SuperSecret123!"})
        api(
            "POST",
            "/setup/network",
            json={
                "wake_interface": "enP4p65s0",
                "default_wake_strategy": "etherwake",
                "default_poll_timeout_s": 60,
            },
        )
        api("POST", "/setup/complete")

    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "SuperSecret123!"})
    csrf = r.json()["csrf_token"]

    # Add demo machines if not present
    existing = s.get(f"{BASE}/api/machines").json()
    names = {m["name"] for m in existing}
    if "Fedora PC" not in names:
        s.post(
            f"{BASE}/api/machines",
            json={
                "name": "Fedora PC",
                "ip_address": "172.24.0.2",
                "mac_address": "d8:bb:c1:cd:d1:c7",
                "wake_strategy": "etherwake",
            },
            headers={"X-CSRF-Token": csrf},
        )
    if "NAS" not in names:
        s.post(
            f"{BASE}/api/machines",
            json={
                "name": "NAS",
                "ip_address": "192.168.1.10",
                "mac_address": "00:11:22:33:44:55",
                "wake_strategy": "udp_broadcast",
            },
            headers={"X-CSRF-Token": csrf},
        )
    return csrf, s


def shot(page, name: str, description: str = "") -> None:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  saved {path.name}  {description}")


# ── main ───────────────────────────────────────────────────────────────────


def main() -> None:
    print("Setting up app state via API...")
    _csrf, api_session = setup_app()
    print("Done. Launching browser...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            color_scheme="light",
        )

        # ── 1. Setup wizard (fresh browser — not logged in) ───────────────
        print("\nShooting setup wizard (redirected from / since already complete)...")
        page = ctx.new_page()
        page.goto(f"{BASE}/login")
        page.wait_for_load_state("networkidle")
        shot(
            page,
            "01_setup_wizard_redirect",
            "Login page (wizard complete, redirects here for anon users)",
        )

        # ── 2. Login page ─────────────────────────────────────────────────
        print("Login page...")
        page2 = ctx.new_page()
        page2.goto(f"{BASE}/login")
        page2.wait_for_load_state("networkidle")
        shot(page2, "02_login", "Login page")

        # ── 3. Log in and shoot dashboard ─────────────────────────────────
        print("Logging in...")
        page2.fill("input[name=username]", "admin")
        page2.fill("input[name=password]", "SuperSecret123!")
        page2.click("button[type=submit]")
        page2.wait_for_url(f"{BASE}/machines", timeout=8000)
        page2.wait_for_load_state("networkidle")
        time.sleep(1)
        shot(
            page2, "03_dashboard_authed", "Dashboard after login — machine list with status badges"
        )

        # ── 4. Probe one machine to show badge update ─────────────────────
        print("Probing machine status...")
        # Click the Probe button for the first machine
        probe_btns = page2.locator("button", has_text="Probe")
        if probe_btns.count() > 0:
            probe_btns.first.click()
            time.sleep(2)
            shot(page2, "04_dashboard_probe", "Dashboard after probe — live state badge")

        # ── 5. Add machine form ───────────────────────────────────────────
        print("Add machine form...")
        page2.goto(f"{BASE}/machines/new")
        page2.wait_for_load_state("networkidle")
        shot(page2, "05_add_machine", "Add machine form")

        # ── 6. Edit machine form ──────────────────────────────────────────
        print("Edit machine form...")
        machines_r = api_session.get(f"{BASE}/api/machines")
        machines = machines_r.json() if machines_r.ok else []
        if machines:
            mid = machines[0]["id"]
            page2.goto(f"{BASE}/machines/{mid}/edit")
            page2.wait_for_load_state("networkidle")
            shot(page2, "06_edit_machine", "Edit machine form")

        # ── 7. Settings page ──────────────────────────────────────────────
        print("Settings page...")
        page2.goto(f"{BASE}/settings")
        page2.wait_for_load_state("networkidle")
        shot(page2, "07_settings", "Settings page")

        # ── 8. Swagger / OpenAPI docs ─────────────────────────────────────
        print("API docs...")
        page3 = ctx.new_page()
        page3.goto(f"{BASE}/api/docs")
        page3.wait_for_load_state("networkidle")
        time.sleep(2)
        shot(page3, "08_api_docs", "Swagger UI")

        # ── 9. Wake modal / action ─────────────────────────────────────────
        print("Wake action from dashboard...")
        page2.goto(f"{BASE}/machines")
        page2.wait_for_load_state("networkidle")
        wake_btns = page2.locator("button", has_text="Wake")
        if wake_btns.count() > 0:
            wake_btns.first.click()
            time.sleep(2)
            shot(page2, "09_wake_dispatched", "Dashboard after wake dispatch")

        browser.close()

    print(f"\nAll screenshots saved to {OUT}/")
    files = sorted(OUT.glob("*.png"))
    for f in files:
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
