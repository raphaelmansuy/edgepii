"""Contrast tests for the demo's palette.

A contrast regression is invisible in a diff and easy to reintroduce, so the
ratios are measured here rather than trusted. WCAG 2.1 AA asks for 4.5:1 on body
text and 3:1 on large text and UI boundaries. Every token in this stylesheet
carries body text somewhere, so the floor applied is 4.5:1 on the darkest
surface it can land on.

The palette is read from `static/styles.css`, not restated, so a change to the
stylesheet is what this test measures.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "apps" / "edgepii-databricks"
CSS = APP_DIR / "static" / "styles.css"

# The surfaces real text sits on, in the order they appear in the UI.
SURFACES = {
    "page": "#05070d",
    "panel": "#101624",
    "code": "#04070e",
    "table": "#0c1220",
}

# Tokens that carry readable text. Every one must clear the body-text floor.
TEXT_TOKENS = (
    "text",
    "muted",
    "faint",
    "accent",
    "accent-2",
    "ok",
    "warn",
    "bad",
    "secret",
    "gov",
    "payment",
    "contact",
    "person",
    "quasi",
)

# Highlight fills, with the ink colour used on top of each.
MARK_INK = "#04070f"
MARK_FILLS = {
    "secret": "#ff5c8a",
    "gov_id": "#ffb454",
    "payment": "#b98cff",
    "contact": "#35e0b6",
    "person": "#5b8cff",
    "quasi": "#8b98ad",
}

BODY_FLOOR = 4.5


def _channel(value: int) -> float:
    srgb = value / 255
    return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    r, g, b = (int(raw[index : index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _live_css() -> str:
    """The stylesheet with comments removed, so prose about a colour is not a usage."""

    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _tokens() -> dict[str, str]:
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", _live_css()))


@pytest.mark.parametrize("name", TEXT_TOKENS)
@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_text_token_clears_the_body_floor(name, surface):
    """Every readable token must pass on every surface it can appear on."""

    tokens = _tokens()
    assert name in tokens, f"--{name} is missing from the stylesheet"
    ratio = contrast(tokens[name], SURFACES[surface])
    assert ratio >= BODY_FLOOR, (
        f"--{name} ({tokens[name]}) on {surface} ({SURFACES[surface]}) "
        f"is {ratio:.2f}:1, below the {BODY_FLOOR}:1 floor"
    )


@pytest.mark.parametrize("name", sorted(MARK_FILLS))
def test_highlight_ink_is_readable_on_its_fill(name):
    """A marked span's text must stay readable, not just the fill distinguishable."""

    ratio = contrast(MARK_INK, MARK_FILLS[name])
    assert ratio >= BODY_FLOOR, f"{name} ink is {ratio:.2f}:1 on {MARK_FILLS[name]}"


def test_the_person_mark_is_not_the_one_exception():
    """Person once used white ink at 3.02:1 while every other mark used dark ink.

    The fill was fine; the unusual text colour was the fault. This asserts the
    stylesheet does not reintroduce a white label on that fill.
    """

    css = _live_css()
    block = re.search(r"mark\.person\s*\{(.*?)\}", css, re.S)
    assert block, "mark.person should exist"
    assert "color: #04070f" in block.group(1), "person mark must use the shared ink"


def test_the_primary_button_label_is_readable_on_both_gradient_stops():
    """A gradient has two ends, and the label must clear the darker one.

    The end stop was #3f6ee0, where the label measured 4.44:1. It is now #3a66d6.
    """

    css = _live_css()
    gradients = re.findall(
        r"linear-gradient\(145deg,\s*var\(--accent\),\s*(#[0-9a-fA-F]{6})\)", css
    )
    assert gradients, "the primary button gradient should exist"
    for stop in set(gradients):
        ratio = contrast("#ffffff", stop)
        assert ratio >= BODY_FLOOR, f"white on {stop} is {ratio:.2f}:1"


def test_the_faint_token_is_not_the_old_contrast_failure():
    """`--faint` carried hint lines at 4.10:1 before. Pin the repair."""

    tokens = _tokens()
    assert tokens["faint"].lower() != "#64718a"
    assert contrast(tokens["faint"], SURFACES["panel"]) >= BODY_FLOOR
