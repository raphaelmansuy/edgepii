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


def _imagemagick() -> str | None:
    """ImageMagick 7 installs `magick`, version 6 installs `convert`."""

    for name in ("magick", "convert"):
        if shutil.which(name):
            return name
    return None


def resize(source: Path, target: Path, width: int) -> bool:
    """Convert to JPEG at `width`, keeping the aspect ratio.

    `sips` resamples by one side only, so a tall image is fitted by height when
    that would otherwise produce a needlessly long file. Both numbers move
    together, so the image is never squashed.

    `sips` is macOS only. On a Linux runner the work goes to ImageMagick, which
    the site workflow already installs for the icons. A PNG copy is the last
    resort, and it is reported, because a copy is not a JPEG.
    """

    dimensions = probe(source)
    target_width = width
    if dimensions and dimensions[0] > 0:
        source_width, source_height = dimensions
        scaled_height = round(source_height * width / source_width)
        if scaled_height > MAX_PIXEL_HEIGHT:
            target_width = round(source_width * MAX_PIXEL_HEIGHT / source_height)

    if shutil.which("sips"):
        args = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(QUALITY)]
        args += ["--resampleWidth", str(target_width)]
        args += [str(source), "--out", str(target)]
        result = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603
        if result.returncode == 0:
            return True

    imagemagick = _imagemagick()
    if imagemagick:
        args = [imagemagick, str(source), "-resize", f"{target_width}x",
                "-quality", str(QUALITY), str(target)]
        result = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603
        if result.returncode == 0:
            return True
        print(f"note: {imagemagick} failed for {source.name}: {result.stderr.strip()[:80]}")

    print(f"note: no JPEG tool for {source.name}, copying the PNG")
    shutil.copy2(source, OUT / f"{source.stem}-{width}.png")
    return True


def probe(path: Path) -> tuple[int, int] | None:
    """Read the pixel size from the file header.

    This used `sips`, which is macOS only, so on a Linux runner the call raised
    and the whole build stopped. The header is a few bytes, and reading it works
    on every host.
    """

    try:
        with path.open("rb") as handle:
            head = handle.read(32)
    except OSError:
        return None

    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")

    # JPEG: walk the segments to the start-of-frame marker.
    if head[:2] == b"\xff\xd8":
        try:
            with path.open("rb") as handle:
                handle.seek(2)
                while True:
                    marker = handle.read(2)
                    if len(marker) < 2:
                        return None
                    if marker[0] != 0xFF:
                        return None
                    kind = marker[1]
                    if kind in (0xD8, 0xD9) or 0xD0 <= kind <= 0xD7:
                        continue
                    length_bytes = handle.read(2)
                    if len(length_bytes) < 2:
                        return None
                    length = int.from_bytes(length_bytes, "big")
                    # SOF0..SOF15, excluding the DHT/JPG/DAC markers.
                    if 0xC0 <= kind <= 0xCF and kind not in (0xC4, 0xC8, 0xCC):
                        body = handle.read(5)
                        if len(body) < 5:
                            return None
                        height = int.from_bytes(body[1:3], "big")
                        width = int.from_bytes(body[3:5], "big")
                        return width, height
                    handle.seek(length - 2, 1)
        except OSError:
            return None
    return None


if __name__ == "__main__":
    raise SystemExit(main())
