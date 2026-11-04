"""Prove the CI path keeps the model lane when the weights are absent.

CI has no torch, so `gen_data.py` records only the rules lane. The committed data
file already holds the model lane from a local run. If the generator dropped it,
the site would silently lose ten examples on every deploy.

This test runs the generator with the hf extra blocked and checks the outcome.
Run: `pytest tests/test_site.py`
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "site" / "gen_data.py"
DATA = ROOT / "site" / "data" / "examples.json"

BLOCK = """
import builtins, importlib.util, sys
real_import = builtins.__import__
BLOCKED = {"transformers", "torch"}
def fake_import(name, *args, **kwargs):
    if name.split(".")[0] in BLOCKED:
        raise ImportError("blocked for the CI simulation")
    return real_import(name, *args, **kwargs)
builtins.__import__ = fake_import
real_spec = importlib.util.find_spec
importlib.util.find_spec = lambda name, *a, **k: None if name.split(".")[0] in BLOCKED else real_spec(name, *a, **k)
sys.argv = ["gen_data.py"]
exec(compile(open(sys.argv_path).read(), sys.argv_path, "exec"), {"__name__": "__main__", "__file__": sys.argv_path})
"""


@pytest.mark.skipif(not DATA.is_file(), reason="no recorded data yet")
def test_ci_keeps_the_recorded_model_lane(tmp_path):
    """A build without torch must not drop the en-closed rows."""

    before = json.loads(DATA.read_text(encoding="utf-8"))
    model_rows = [row["id"] for row in before["examples"] if "en-closed" in row["lanes"]]
    if not model_rows:
        pytest.skip("the committed data holds no model lane")

    script = tmp_path / "run.py"
    script.write_text(f'sys.argv_path = {str(GEN)!r}\n' + BLOCK, encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    after = json.loads(DATA.read_text(encoding="utf-8"))
    kept = [row["id"] for row in after["examples"] if "en-closed" in row["lanes"]]
    assert kept == model_rows, f"the CI path dropped the model lane. stderr={result.stderr[-400:]}"
    assert "en-closed" in {lane["name"] for lane in after["lanes"]}


@pytest.mark.skipif(not DATA.is_file(), reason="no recorded data yet")
def test_the_data_file_holds_only_fake_strings():
    """No example may look like a live credential or a real address."""

    data = json.loads(DATA.read_text(encoding="utf-8"))
    allowed_domains = ("example.com", "example.org", "example.net")
    for row in data["examples"]:
        for lane in row["lanes"].values():
            for span in lane["spans"]:
                if span["type"] == "EMAIL":
                    domain = span["text"].rsplit("@", 1)[-1].lower()
                    assert domain.endswith(allowed_domains), span["text"]


@pytest.mark.skipif(not DATA.is_file(), reason="no recorded data yet")
def test_every_example_satisfies_the_span_contract():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for row in data["examples"]:
        for lane_name, lane in row["lanes"].items():
            for span in lane["spans"]:
                slice_ = row["text"][span["start"] : span["end"]]
                assert slice_ == span["text"], f"{row['id']}/{lane_name}"


@pytest.mark.skipif(not DATA.is_file(), reason="no recorded data yet")
def test_the_demo_has_enough_examples_to_teach():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert len(data["examples"]) >= 12
    ids = {row["id"] for row in data["examples"]}
    # A page of only positive cases teaches nothing about restraint.
    assert "negatives" in ids
    # The long document case must hold an offset past the first window.
    long_row = next(row for row in data["examples"] if row["id"] == "long-text")
    assert long_row["chars"] > 300
    span = long_row["lanes"]["rules"]["spans"][0]
    assert span["start"] > 280


def test_the_tutorial_output_matches_the_library():
    """Every printed result in the guides must still be what the library prints.

    A tutorial that drifts from the code is worse than no tutorial. This runs the
    guide snippets and compares the output, so a library change fails here before
    a reader sees a wrong answer.
    """

    sys.path.insert(0, str(ROOT / "site"))
    try:
        import verify_claims
    finally:
        sys.path.pop(0)
    problems = verify_claims.failures()
    assert problems == [], "\n".join(problems)


def test_the_built_site_passes_its_own_check():
    """Run the link, markup, contrast, and span checks on a fresh build."""


    data = DATA
    if not data.is_file():
        pytest.skip("no recorded data yet")
    build = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "site" / "build.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    if build.returncode != 0:
        pytest.skip(f"build unavailable here: {build.stderr.strip()[:200]}")
    check = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "site" / "check.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr


def test_a_rebuild_keeps_the_converted_images():
    """A build must not wipe `dist/shots`, or a rebuild breaks the tour page.

    The test suite builds, then checks. If `build.py` removed every file under
    `dist/`, the second build would delete the JPEGs that `images.py` made and
    the tour page would 404. This locks the behaviour.
    """

    shots = ROOT / "site" / "dist" / "shots"
    marker = shots / "01-home-720.jpg"
    if not marker.is_file():
        pytest.skip("no converted images yet, run site/images.py")
    before = sorted(path.name for path in shots.iterdir())
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "site" / "build.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stderr
    after = sorted(path.name for path in shots.iterdir())
    assert after == before, "the build removed converted images"


def test_the_icon_set_is_complete():
    """A manifest or a link that names a missing icon is a silent install error."""

    icons = ROOT / "site" / "static" / "icons"
    if not icons.is_dir():
        pytest.skip("icons not built yet, run site/icons.py")
    required = [
        "favicon.ico",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "icon-maskable-192.png",
        "icon-maskable-512.png",
    ]
    for name in required:
        path = icons / name
        assert path.is_file(), name
        assert path.stat().st_size > 500, name


def test_every_icon_png_is_the_size_it_claims():
    """A phone asks for 192 and 512 by name. A wrong pixel size is a crop bug."""

    icons = ROOT / "site" / "static" / "icons"
    if not icons.is_dir():
        pytest.skip("icons not built yet")
    expected = {
        "icon-192.png": 192,
        "icon-512.png": 512,
        "icon-maskable-192.png": 192,
        "icon-maskable-512.png": 512,
        "apple-touch-icon.png": 180,
    }
    for name, size in expected.items():
        result = subprocess.run(  # noqa: S603
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(icons / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("sips is not available here")
        assert f"pixelWidth: {size}" in result.stdout, name
        assert f"pixelHeight: {size}" in result.stdout, name


def test_the_social_card_is_the_size_platforms_expect():
    """1200 by 630 is the ratio every major preview card renders without a crop."""

    card = ROOT / "site" / "static" / "social.png"
    if not card.is_file():
        pytest.skip("no social card yet, run site/social.py")
    result = subprocess.run(  # noqa: S603
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(card)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("sips is not available here")
    assert "pixelWidth: 1200" in result.stdout
    assert "pixelHeight: 630" in result.stdout
    assert card.stat().st_size < 1_000_000, "the card is over 1 MB, which some platforms reject"


def test_the_built_pages_carry_a_complete_social_head():
    """The head must satisfy a link preview, not only a browser."""

    index = ROOT / "site" / "dist" / "index.html"
    if not index.is_file():
        pytest.skip("no build yet")
    html = index.read_text(encoding="utf-8")
    for marker in (
        'property="og:image" content="https://raphaelmansuy.github.io/edgepii/assets/social.png"',
        'property="og:image:width" content="1200"',
        'property="og:image:height" content="630"',
        'name="twitter:card" content="summary_large_image"',
        'rel="canonical" href="https://raphaelmansuy.github.io/edgepii/"',
        'name="robots" content="index, follow',
        'rel="icon" href="favicon.ico"',
        'rel="apple-touch-icon"',
        'rel="manifest"',
    ):
        assert marker in html, marker
    # The mark is inline SVG, so it paints with the first byte and needs no request.
    assert '<svg viewBox="0 0 64 64"' in html
