#!/usr/bin/env python3
"""Check the customer-facing report no longer includes the Founding Pilot line."""

from __future__ import annotations

import http.server
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PORT = 8767
BASE = f"http://127.0.0.1:{PORT}"
FAILURES: list[str] = []
PDF_OUT = Path("/workspace/field-app/wsa_example_report_no_founding_pilot.pdf")


class SpaHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/" and not (ROOT / path.lstrip("/")).is_file():
            self.path = "/404.html"
        return super().do_GET()


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print("FAIL:", msg)


def ok(msg: str) -> None:
    print("PASS:", msg)


def assert_copy(label: str, text: str) -> None:
    low = text.lower()
    if "founding pilot" in low or "$1,000" in text:
        fail(f"{label} still has Founding Pilot or $1,000")
        return
    if "$1,500" in text and "credited toward the first retainer month" in text:
        ok(f"{label} has the $1,500 evaluation credit line and no Founding Pilot")
    else:
        fail(f"{label} missing $1,500 credited-toward-first-month wording")


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), SpaHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.2)

    shot_dir = Path("/workspace/field-app")
    shot_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            accept_downloads=True,
        )
        page = context.new_page()
        page.goto(f"{BASE}/a/example-northline/report", wait_until="networkidle", timeout=30000)
        page.wait_for_selector("text=Export PDF", timeout=15000)
        time.sleep(0.8)
        page.screenshot(path=str(shot_dir / "report-next-steps-no-founding-pilot.png"), full_page=True)
        body = page.inner_text("body")
        assert_copy("on-screen report", body)

        PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
        try:
            with page.expect_download(timeout=30000) as di:
                page.click("text=Export PDF")
            download = di.value
            download.save_as(str(PDF_OUT))
            ok(f"PDF exported ({PDF_OUT.stat().st_size} bytes)")
        except Exception as e:
            fail(f"PDF export failed: {type(e).__name__}: {e}")
            server.shutdown()
            return 1

        # Migration: put the old Founding Pilot offer back, reload, confirm it is stripped
        page.evaluate(
            """async () => {
              const db = await new Promise((resolve, reject) => {
                const req = indexedDB.open('wsa-site-assessment');
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
              });
              const tx = db.transaction('settings', 'readwrite');
              const store = tx.objectStore('settings');
              const current = await new Promise((resolve, reject) => {
                const r = store.get('app');
                r.onsuccess = () => resolve(r.result);
                r.onerror = () => reject(r.error);
              });
              if (!current || !current.offer) throw new Error('no settings');
              current.offer.offers = [
                ...current.offer.offers.filter((o) => o.id !== 'deployment'),
                {
                  id: 'deployment',
                  name: 'wsafe.ai deployment',
                  price: '$1,000 · 30 days · no install fee',
                  detail: 'Founding Pilot. Put your existing cameras to work on a paid founding pilot.',
                },
              ];
              await new Promise((resolve, reject) => {
                const r = store.put(current);
                r.onsuccess = () => resolve();
                r.onerror = () => reject(r.error);
              });
              await new Promise((resolve, reject) => {
                tx.oncomplete = () => resolve();
                tx.onerror = () => reject(tx.error);
              });
              db.close();
            }"""
        )
        page.reload(wait_until="networkidle")
        page.wait_for_selector("text=Export PDF", timeout=15000)
        time.sleep(0.6)
        migrated = page.inner_text("body")
        assert_copy("report after migrating a saved Founding Pilot offer", migrated)

        context.close()
        browser.close()

    text = subprocess.check_output(["pdftotext", "-layout", str(PDF_OUT), "-"], text=True)
    Path("/workspace/field-app/wsa_example_report_no_founding_pilot.txt").write_text(text)
    assert_copy("exported PDF", text)

    server.shutdown()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed")
        return 1
    print("\nAll offer-wording checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
