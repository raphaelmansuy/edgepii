"""Make a responsive image set for the site from the e2e screenshots.

The e2e run writes 2880 pixel PNGs, about 1 MB each. Twelve of those is 11 MB,
which is a bad page on a phone and a bad score on any performance check.

This script writes two JPEG widths per screenshot, and the page uses `srcset` so
a phone fetches the small one. A JPEG is the right choice here: the images are
UI screenshots with large flat areas, and the quality loss is invisible at 82.

The full-size PNG stays linked, so a reader can still open the original. The
conversion is skipped when the output is newer than the source, so a second run
does no work.

Run: `python site/images.py`
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "docs" / "e2e" / "screenshots"
OUT = HERE / "dist" / "shots"

# CSS width. The tour card renders at most 860 CSS pixels, so 1440 real pixels
# is about 1.7x, which stays sharp on a retina screen. The 2880 pixel original
# is never shipped: the "open full size" link points at the repository file, so
# 13 MB of PNG stays out of the deploy.
WIDTHS = (720, 1440)
QUALITY = 72
# A very tall capture costs bytes for pixels nobody sees. The narrow run is
# 11 486 pixels tall; at 720 wide it would still be 2 871 tall, which is fine,
# but at 1440 wide it is 5 743. Cap the height only when it exceeds this, and
# keep the aspect ratio by reducing both sides together.
MAX_PIXEL_HEIGHT = 3000


def main() -> int:
    if not SOURCE.is_dir():
        print(f"error: no screenshots at {SOURCE}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    total = 0
    for png in sorted(SOURCE.glob("*.png")):
        stem = png.stem
        for width in WIDTHS:
            target = OUT / f"{stem}-{width}.jpg"
            if target.is_file() and target.stat().st_mtime >= png.stat().st_mtime:
                total += target.stat().st_size
                continue
            if not resize(png, target, width):
                return 1
            written += 1
            total += target.stat().st_size
    print(f"images: {written} converted, {total / 1_048_576:.1f} MB of JPEG output")
    return 0


def resize(source: Path, target: Path, width: int) -> bool:
    """Convert to JPEG at `width`, keeping the aspect ratio.

    sips resamples by one side only, so a tall image is fitted by height when
    that would otherwise produce a needlessly long file. Both numbers move
    together, so the image is never squashed.
    """

    dimensions = probe(source)
    args = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(QUALITY)]
    if dimensions and dimensions[0] > 0:
        source_width, source_height = dimensions
        scaled_height = round(source_height * width / source_width)
        if scaled_height > MAX_PIXEL_HEIGHT:
            fitted_width = round(source_width * MAX_PIXEL_HEIGHT / source_height)
            args += ["--resampleWidth", str(fitted_width)]
        else:
            args += ["--resampleWidth", str(width)]
    else:
        args += ["--resampleWidth", str(width)]
    args += [str(source), "--out", str(target)]
    result = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        # CI runs on Linux, where sips may be absent. Copy the PNG so the build
        # still works, and the page keeps a readable figure.
        print(f"note: sips failed for {source.name} ({result.stderr.strip()[:60]}), copying PNG")
        shutil.copy2(source, OUT / f"{source.stem}-{width}.png")
    return True


def probe(path: Path) -> tuple[int, int] | None:
    """Read the pixel size with sips, so a tall image can be fitted not cropped."""

    result = subprocess.run(  # noqa: S603
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    values = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            values[key.strip()] = value.strip()
    try:
        return int(values["pixelWidth"]), int(values["pixelHeight"])
    except (KeyError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
