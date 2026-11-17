#!/usr/bin/env python3
"""Regression checks for the boot / white-screen fix. Serves this repo locally."""

from __future__ import annotations

import http.server
import os
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
FAILURES: list[str] = []


class SpaHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        fs = ROOT / path.lstrip("/")
        if path != "/" and not fs.is_file():
            self.path = "/404.html"
        return super().do_GET()


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print("FAIL:", msg)


def ok(msg: str) -> None:
    print("PASS:", msg)


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), SpaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")

        # 1. Home screen loads
        page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=30000)
        page.wait_for_selector("text=New assessment", timeout=8000)
        if "Site assessments" in page.inner_text("body"):
            ok("home screen loads")
        else:
            fail("home screen missing title")

        # 2. Example assessment opens
        page.goto(f"{BASE}/a/example-northline", wait_until="networkidle")
        page.wait_for_selector("text=Start walkthrough", timeout=8000)
        body = page.inner_text("body")
        if "Northline Yard" in body and "Start walkthrough" in body:
            ok("example assessment opens")
        else:
            fail("example assessment did not open")

        # 3. Unknown route is not a blank screen
        page.goto(f"{BASE}/assessments", wait_until="networkidle")
        page.wait_for_timeout(500)
        body = page.inner_text("body").strip()
        if "This page is not in the app" in body or "Back to assessments" in body:
            ok("unknown route shows recovery, not a blank screen")
        else:
            fail(f"unknown route still blank or unexpected: {body[:200]!r}")

        # 4. Missing assessment does not hang on Opening…
        page.goto(f"{BASE}/a/does-not-exist", wait_until="networkidle")
        page.wait_for_timeout(1500)
        body = page.inner_text("body").strip()
        if "not on this device" in body and "Opening this assessment" not in body:
            ok("missing assessment shows not-found, does not hang")
        else:
            fail(f"missing assessment hung or unexpected: {body[:200]!r}")

        page.close()

        # 5. IndexedDB failure still paints a recovery screen
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page = context.new_page()
        page.add_init_script(
            """
            const failing = {
              open() {
                const r = {};
                queueMicrotask(() => {
                  r.error = new DOMException('InvalidStateError', 'InvalidStateError');
                  if (r.onerror) r.onerror({ target: r });
                });
                return r;
              },
              deleteDatabase() { return failing.open(); },
              cmp() { return 0; }
            };
            Object.defineProperty(window, 'indexedDB', { configurable: true, get() { return failing; } });
            """
        )
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(5000)
        body = (page.inner_text("body") or "").strip()
        root_count = page.evaluate("() => (document.getElementById('root')||{}).childElementCount || 0")
        recovered = "This screen hit a problem" in body or "This screen could not open" in body or "Back to assessments" in body or "Reload" in body
        if root_count > 0 and recovered and body:
            ok("IndexedDB failure shows a recovery screen, not a blank page")
        else:
            fail(f"IndexedDB failure still blank: children={root_count} body={body[:200]!r}")
        context.close()
        browser.close()

    server.shutdown()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed")
        return 1
    print("\nAll boot-recovery checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
