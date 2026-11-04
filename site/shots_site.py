"""Screenshot the built site with Playwright, so a visual check needs no server tab.

The embedded browser cannot always reach a localhost port, and a static build
needs no interactivity to review. This renders the pages Chromium would render,
at fixed viewports, and writes a PNG per page.

Run: `python site/shots_site.py`
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dist"
SHOTS = Path("/tmp/site-shots")
PORT = 8097
BASE = f"http://127.0.0.1:{PORT}"

PAGES = [
    ("home", ""),
    ("demo", "demo/"),
    ("examples", "guide-examples/"),
    ("evaluation", "evaluation/"),
    ("start", "start/"),
    ("doc-api", "doc-api/"),
]


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "--directory", str(OUT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"{BASE}/", timeout=1).read()
                break
            except OSError:
                time.sleep(0.25)
        else:
            print("error: the server did not come up", file=sys.stderr)
            return 1

        from playwright.sync_api import sync_playwright

        with sync_playwright() as driver:
            browser = driver.chromium.launch()
            for name, route in PAGES:
                for label, width, height in (("desktop", 1440, 900), ("mobile", 390, 844)):
                    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
                    page.goto(f"{BASE}/{route}", wait_until="networkidle")
                    page.evaluate("document.fonts.ready.then(() => true)")
                    page.wait_for_timeout(250)
                    target = SHOTS / f"{name}-{label}.png"
                    page.screenshot(path=str(target), full_page=(label == "desktop"))
                    print(f"  {target.name} {target.stat().st_size / 1024:.0f} KB")
                    page.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
    print(f"shots in {SHOTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
