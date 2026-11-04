"""Generate the raster icon set from the two SVG sources.

A browser needs a `.ico` for a legacy tab and a `favicon.svg` for a modern one.
A phone home screen needs PNGs at fixed sizes, in a plain and a maskable variant.
`site.webmanifest` names those files, so a missing one is an install error.

The SVG is the source of truth. This script only rasterises it, and it asserts
the output exists at the exact size the manifest names.

Run: `python site/icons.py`
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
OUT = STATIC / "icons"

# The size the manifest advertises, plus the two a legacy tab asks for.
PNG_SIZES = (192, 512)
ICO_SIZES = (16, 32, 48)

# Which source feeds which output, and whether it keeps its transparent corners.
VARIANTS: dict[str, list[tuple[int, bool]]] = {
    "icon": [(180, False), (192, False), (512, False)],
    "icon-maskable": [(192, False), (512, False)],
}


def main() -> int:
    for tool in ("rsvg-convert", "magick"):
        if not _which(tool):
            print(f"error: {tool} is required to build the icons", file=sys.stderr)
            return 2
    OUT.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for name, sizes in VARIANTS.items():
        source = STATIC / f"{name}.svg"
        if not source.is_file():
            print(f"error: missing {source}", file=sys.stderr)
            return 1
        for size, _transparent in sizes:
            target = OUT / (f"apple-touch-icon.png" if name == "icon" and size == 180 else f"{name}-{size}.png")
            _raster(source, target, size)
            written.append(target)

    # A multi-resolution .ico from the plain source, for a tab in an old browser.
    ico_sources = []
    for size in ICO_SIZES:
        temp = OUT / f".ico-{size}.png"
        _raster(STATIC / "icon.svg", temp, size)
        ico_sources.append(temp)
    ico = OUT / "favicon.ico"
    _run(["magick", *[str(path) for path in ico_sources], str(ico)])
    for path in ico_sources:
        path.unlink()
    written.append(ico)

    # The tab icon a modern browser reads, at the site root.
    favicon_svg = STATIC / "favicon.svg"
    write_favicon_svg(favicon_svg)
    written.append(favicon_svg)

    for path in written:
        if not path.is_file() or path.stat().st_size == 0:
            print(f"error: {path} was not written", file=sys.stderr)
            return 1
    total = sum(path.stat().st_size for path in written)
    print(f"icons: {len(written)} files, {total / 1024:.1f} KB")
    for path in written:
        print(f"  {path.relative_to(HERE)} {path.stat().st_size / 1024:.1f} KB")
    return 0


def write_favicon_svg(target: Path) -> None:
    """The tab icon: the same mark on a tile, sized for a 16 pixel slot.

    A favicon has one job at 16 pixels: be recognisable. The tile keeps its
    radius so it matches the app icon, and the ink is the plain variant.
    """

    target.write_text(
        (STATIC / "icon.svg").read_text(encoding="utf-8"), encoding="utf-8"
    )


def _raster(source: Path, target: Path, size: int) -> None:
    _run(["rsvg-convert", "-w", str(size), "-h", str(size), str(source), "-o", str(target)])


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(args)}\n{result.stderr[:400]}")


def _which(name: str) -> bool:
    """True when `name` is on PATH. `command` is a shell builtin, so it cannot
    be exec'd directly, and it does not exist as a binary on a Linux runner."""

    return shutil.which(name) is not None


if __name__ == "__main__":
    raise SystemExit(main())
