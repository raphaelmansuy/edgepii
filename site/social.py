"""Render the Open Graph card to PNG with the site's real webfonts.

Most link previews will not draw an SVG, so the card must be a PNG at 1200 by
630. `rsvg-convert` would rasterise the SVG, but it has no access to Inter and
JetBrains Mono as the browser sees them, so the card would show a fallback face
that does not match the site.

Chromium does have them. This script loads the same Google Fonts stylesheet the
site uses, waits for `document.fonts.ready`, then screenshots a 1200 by 630
viewport at a device scale of 1. The wait matters: a screenshot taken before the
fonts settle ships a card with the wrong typeface and no error.

If Playwright or Chromium is missing, the script falls back to rasterising the
SVG and says so. A fallback card beats no card.

Run: `python site/social.py`
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
OUT = STATIC / "social.png"
VIEWPORT = {"width": 1200, "height": 630}

CSS = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;500&display=swap"
)


def main() -> int:
    svg = (STATIC / "social.svg").read_text(encoding="utf-8")
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{CSS}" rel="stylesheet">
<style>
  html,body{{margin:0;padding:0;background:#070b14;width:{VIEWPORT['width']}px;height:{VIEWPORT['height']}px;overflow:hidden}}
  svg{{display:block}}
</style></head><body>{svg}</body></html>
"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("note: playwright is absent, falling back to rsvg-convert", file=sys.stderr)
        return rasterise_svg()

    try:
        with sync_playwright() as driver:
            browser = driver.chromium.launch()
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
            page.set_content(html, wait_until="networkidle")
            page.evaluate("document.fonts.ready.then(() => true)")
            page.wait_for_timeout(350)
            faces = page.evaluate(
                "Array.from(document.fonts).filter(f => f.status === 'loaded')"
                ".map(f => f.family + ' ' + f.weight)"
            )
            page.screenshot(path=str(OUT), type="png", clip={"x": 0, "y": 0, **VIEWPORT})
            browser.close()
    except Exception as exc:  # noqa: BLE001 - a missing browser must not stop the build
        print(f"note: chromium failed ({type(exc).__name__}), falling back", file=sys.stderr)
        return rasterise_svg()

    if not OUT.is_file() or OUT.stat().st_size == 0:
        return rasterise_svg()
    if not any("Inter" in face for face in faces):
        print("warning: Inter did not load, so the card uses a fallback face", file=sys.stderr)
    print(f"social: {OUT.relative_to(HERE)} {OUT.stat().st_size / 1024:.1f} KB, fonts {sorted(set(faces))[:4]}")
    return 0


def rasterise_svg() -> int:
    result = subprocess.run(  # noqa: S603
        ["rsvg-convert", "-w", str(VIEWPORT["width"]), "-h", str(VIEWPORT["height"]),
         str(STATIC / "social.svg"), "-o", str(OUT)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"error: could not render the social card: {result.stderr[:200]}", file=sys.stderr)
        return 1
    print(f"social: {OUT.relative_to(HERE)} {OUT.stat().st_size / 1024:.1f} KB (rsvg fallback)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
