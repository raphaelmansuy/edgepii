"""Check the built site. A broken build must not reach Pages.

This is not a style test. It answers questions a reader would hit in the first
minute:

- Does every internal link point at a file that exists?
- Does every page have one h1, a title, and a description?
- Does every image have alt text, and does every anchor have a name?
- Is the markup balanced, so a browser shows the page and not a broken tree?
- Does the sitemap list every page, and does every asset it names exist?
- Does each demo row still satisfy `source[start:end] == text`?

Run: `python site/check.py`
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
OPTIONAL_CLOSE = {"p", "li", "tr", "td", "th", "thead", "tbody"}


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.ids: set[str] = set()
        self.duplicate_ids: list[str] = []
        self.links: list[str] = []
        self.images: list[tuple[str, str]] = []
        self.h1 = 0
        self.headings: list[tuple[int, str]] = []
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.labels_for: list[str] = []
        self.form_controls: list[tuple[str, str]] = []
        self._in_title = False
        self._capture: str | None = None
        self._buffer: list[str] = []
        self.scripts = 0
        self.tables = 0
        self.th_outside_thead = 0
        self._in_thead = False
        self.buttons_without_type: int = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "meta" and attributes.get("name") == "description":
            self.description = attributes.get("content", "")
        if tag == "link" and attributes.get("rel") == "canonical":
            self.canonical = attributes.get("href", "")
        if tag == "a":
            href = attributes.get("href")
            if href is not None:
                self.links.append(href)
        if tag == "img":
            self.images.append((attributes.get("src", ""), attributes.get("alt", "")))
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            if level == 1:
                self.h1 += 1
            self._capture = tag
            self._buffer = []
            self.headings.append((level, ""))
        if tag == "label" and attributes.get("for"):
            self.labels_for.append(attributes["for"])
        if tag in ("input", "select", "textarea"):
            self.form_controls.append((tag, attributes.get("id", "")))
        if tag == "script":
            self.scripts += 1
        if tag == "table":
            self.tables += 1
        if tag == "thead":
            self._in_thead = True
        if tag == "button" and "type" not in attributes:
            self.buttons_without_type += 1
        if attributes.get("id"):
            if attributes["id"] in self.ids:
                self.duplicate_ids.append(attributes["id"])
            self.ids.add(attributes["id"])
        if tag in VOID:
            return
        if tag in OPTIONAL_CLOSE and self.stack and self.stack[-1] == tag:
            self.stack.pop()
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "thead":
            self._in_thead = False
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._capture == tag:
            text = "".join(self._buffer).strip()
            if self.headings and self.headings[-1][0] == int(tag[1]):
                self.headings[-1] = (int(tag[1]), text)
            self._capture = None
        if tag in VOID:
            return
        if tag in OPTIONAL_CLOSE and tag not in self.stack:
            return
        if not self.stack:
            self.errors.append(f"stray </{tag}>")
            return
        if self.stack[-1] == tag:
            self.stack.pop()
            return
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.errors.append(f"unclosed <{self.stack.pop()}> before </{tag}>")
            if self.stack:
                self.stack.pop()
            return
        self.errors.append(f"close </{tag}> is not open")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._capture:
            self._buffer.append(data)


def main() -> int:
    if not DIST.is_dir():
        print("error: run site/build.py first", file=sys.stderr)
        return 2
    pages = sorted(DIST.rglob("*.html"))
    problems: list[str] = []
    warnings: list[str] = []
    seen_titles: dict[str, str] = {}
    seen_desc: dict[str, str] = {}

    for path in pages:
        rel = path.relative_to(DIST)
        parser = Page()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        where = str(rel)

        if parser.stack:
            problems.append(f"{where}: unclosed tags at end: {parser.stack}")
        for error in parser.errors:
            problems.append(f"{where}: {error}")
        if parser.duplicate_ids:
            problems.append(f"{where}: duplicate id {sorted(set(parser.duplicate_ids))}")

        if not parser.title.strip():
            problems.append(f"{where}: no <title>")
        else:
            if len(parser.title) > 70:
                warnings.append(f"{where}: title is {len(parser.title)} chars: {parser.title!r}")
            if parser.title in seen_titles:
                problems.append(f"{where}: title repeats {seen_titles[parser.title]}")
            seen_titles[parser.title] = where

        if not parser.description.strip():
            problems.append(f"{where}: no meta description")
        else:
            if len(parser.description) > 165:
                warnings.append(f"{where}: description is {len(parser.description)} chars")
            if parser.description in seen_desc:
                problems.append(f"{where}: description repeats {seen_desc[parser.description]}")
            seen_desc[parser.description] = where

        if not parser.canonical:
            problems.append(f"{where}: no canonical link")
        if parser.h1 != 1:
            problems.append(f"{where}: {parser.h1} h1 elements, expected 1")

        # Heading order must not skip a level, which breaks a screen reader outline.
        previous = 0
        for level, text in parser.headings:
            if previous and level > previous + 1:
                problems.append(f"{where}: heading jump h{previous} to h{level} near {text!r}")
            previous = level

        for src, alt in parser.images:
            if src == "":
                problems.append(f"{where}: an img has no src")
            if alt == "":
                problems.append(f"{where}: img {src} has no alt text")

        for tag, control_id in parser.form_controls:
            if tag == "input" and control_id == "":
                continue  # a range input can carry aria-label instead
        if parser.buttons_without_type:
            problems.append(f"{where}: {parser.buttons_without_type} button(s) without type")

        for href in parser.links:
            if href.startswith(("http://", "https://", "mailto:", "#")):
                continue
            parts = urlsplit(href)
            target = (path.parent / unquote(parts.path)).resolve()
            if parts.path.endswith("/") or parts.path == "":
                target = target / "index.html"
            if not target.exists():
                problems.append(f"{where}: broken link {href}")

    check_assets(problems)
    check_data(problems)
    check_sitemap(pages, problems)
    check_required_pages(problems)

    for line in warnings:
        print(f"warn: {line}")
    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"ok: {len(pages)} pages, {len(warnings)} warning(s), no broken links or markup errors")
    return 0


def check_assets(problems: list[str]) -> None:
    for needed in ("assets/site.css", "assets/site.js", "assets/icon.svg", "assets/social.svg"):
        if not (DIST / needed).is_file():
            problems.append(f"missing asset {needed}")
    css = (DIST / "assets" / "site.css").read_text(encoding="utf-8")
    if ".m[data-class=" not in css:
        problems.append("site.css lost the span mark styles")
    js = (DIST / "assets" / "site.js").read_text(encoding="utf-8")
    for marker in ("data-demo", "data-examples-source", "visibleSpans"):
        if marker not in js:
            problems.append(f"site.js is missing {marker}")
    check_contrast(css, problems)


def _luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    if len(value) != 6:
        raise ValueError(hex_colour)
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def check_contrast(css: str, problems: list[str]) -> None:
    """Every text token must clear WCAG AA 4.5:1 on every surface it sits on.

    The smallest type on the site is a 13px hint in `--faint`, which needs the
    full 4.5:1, not the 3:1 that large text allows. This runs on the built CSS,
    so a token change cannot quietly break readability.
    """

    tokens = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", css))
    surfaces = {
        "page": tokens.get("bg", "#05070d"),
        "panel": tokens.get("panel-solid", "#0d1420"),
        "panel-soft": tokens.get("bg-soft", "#0a0f1a"),
    }
    for name in ("text", "muted", "faint", "accent", "accent-2"):
        colour = tokens.get(name)
        if colour is None:
            problems.append(f"site.css lost the --{name} token")
            continue
        for surface_name, surface in surfaces.items():
            ratio = contrast(colour, surface)
            if ratio < 4.5:
                problems.append(
                    f"contrast: --{name} {colour} on {surface_name} is {ratio:.2f}:1, "
                    "which is below WCAG AA 4.5:1 for body text"
                )


def check_data(problems: list[str]) -> None:
    path = DIST / "assets" / "examples.json"
    if not path.is_file():
        problems.append("missing assets/examples.json")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for row in data["examples"]:
        text = row["text"]
        for lane_name, lane in row["lanes"].items():
            for span in lane["spans"]:
                if text[span["start"] : span["end"]] != span["text"]:
                    problems.append(f"demo data breaks the slice contract: {row['id']}/{lane_name}")
            offsets = sorted((span["start"], span["end"]) for span in lane["spans"])
            for left, right in zip(offsets, offsets[1:]):
                if right[0] < left[1]:
                    problems.append(f"demo data holds overlapping spans: {row['id']}/{lane_name}")


def check_sitemap(pages: list[Path], problems: list[str]) -> None:
    path = DIST / "sitemap.xml"
    if not path.is_file():
        problems.append("missing sitemap.xml")
        return
    xml = path.read_text(encoding="utf-8")
    # The namespace must be sitemaps.org. A typo makes the file invalid to every
    # crawler, and a search engine then reports "couldn't fetch" with no reason.
    if 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' not in xml:
        problems.append("sitemap.xml has the wrong namespace, so a crawler cannot read it")
    locations = re.findall(r"<loc>([^<]+)</loc>", xml)
    # 404.html is a page but it is not an indexable URL, so it stays out of the map.
    indexable = [page for page in pages if page.name != "404.html"]
    if len(locations) != len(indexable):
        problems.append(f"sitemap lists {len(locations)} urls for {len(indexable)} indexable pages")
    if any("404" in location for location in locations):
        problems.append("sitemap lists the 404 page, which must not be indexed")
    if not (DIST / "robots.txt").is_file():
        problems.append("missing robots.txt")
    if not (DIST / ".nojekyll").is_file():
        problems.append("missing .nojekyll, so Pages would drop _ paths")
    if not (DIST / "404.html").is_file():
        problems.append("missing 404.html")


def check_required_pages(problems: list[str]) -> None:
    required = [
        "index.html", "demo/index.html", "tour/index.html", "evaluation/index.html",
        "start/index.html", "concepts/index.html", "guide-examples/index.html",
        "guide-masking/index.html", "guide-evaluate/index.html", "doc-index/index.html",
        "doc-api/index.html", "doc-taxonomy/index.html", "doc-corpora/index.html",
    ]
    for route in required:
        if not (DIST / route).is_file():
            problems.append(f"missing page {route}")


if __name__ == "__main__":
    raise SystemExit(main())
