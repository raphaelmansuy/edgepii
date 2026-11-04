"""Rewrite the relative links inside a repo doc so they work on the site.

A doc says `[the API](06-library-api.md)`. The site serves that file at
`/doc-api/`. Without a rewrite, every cross-reference in the specification is a
404. This module is the one place that knows the mapping, so a new doc needs one
row and nothing else.
"""

from __future__ import annotations

import re

# Source file name, relative to docs/, to site route.
DOC_ROUTES: dict[str, str] = {
    "README.md": "doc-index",
    "00-five-whys.md": "doc-why",
    "01-span-contract.md": "doc-span-contract",
    "02-first-principles.md": "doc-first-principles",
    "03-ai-engineering.md": "doc-ai-engineering",
    "04-research-landscape.md": "doc-landscape",
    "05-model-catalog.md": "doc-catalog",
    "06-library-api.md": "doc-api",
    "07-architecture.md": "doc-architecture",
    "08-implementation-plan.md": "doc-plan",
    "09-evaluation.md": "doc-evaluation",
    "10-taxonomy.md": "doc-taxonomy",
    "11-examples.md": "guide-examples",
    "12-public-corpora.md": "doc-corpora",
    "13-first-public-score.md": "doc-score",
    "14-assessment-2026-11.md": "doc-assessment",
    "glossary.md": "doc-glossary",
    # Pages that live outside docs/ but get a route of their own.
    "START.md": "start",
    "CONCEPTS.md": "concepts",
    "GUIDE-MASKING.md": "guide-masking",
    "GUIDE-EVALUATE.md": "guide-evaluate",
    "GUIDE-EXAMPLES.md": "guide-examples",
}

# A doc can link to the package README, which has no route of its own.
EXTRA_ROUTES = {"../README.md": "doc-index"}

_LINK = re.compile(r"\]\(([^)\s]+)\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


def rewrite(markdown: str, depth: int = 1) -> str:
    """Point an internal link at the built route. External links stay as they are.

    `depth` is how many directories deep the page sits. Every route is one
    directory deep (`/doc-api/index.html`), so the default is 1.
    """

    prefix = "../" * depth

    def fix_image(match: re.Match[str]) -> str:
        alt, target = match.group(1), match.group(2)
        if target.startswith("docs/e2e/screenshots/"):
            return f"![{alt}]({prefix}shots/{target.rsplit('/', 1)[-1]})"
        if target.startswith("e2e/screenshots/"):
            return f"![{alt}]({prefix}shots/{target.rsplit('/', 1)[-1]})"
        if target.startswith("http"):
            return match.group(0)
        return match.group(0)

    def fix_link(match: re.Match[str]) -> str:
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            return match.group(0)
        path, _, anchor = target.partition("#")
        suffix = f"#{anchor}" if anchor else ""
        if path in EXTRA_ROUTES:
            return f"]({prefix}{EXTRA_ROUTES[path]}/{suffix})"
        name = path.rsplit("/", 1)[-1]
        if name in DOC_ROUTES:
            return f"]({prefix}{DOC_ROUTES[name]}/{suffix})"
        if path.startswith("docs/e2e/screenshots/"):
            return f"]({prefix}shots/{path.rsplit('/', 1)[-1]})"
        # An ADR, the corpora YAML, or any other repo file. Send the reader to
        # the source, because the site does not carry it.
        if path.startswith(("adr/", "src/", "../src/", "modal/", "demo/", "tests/")):
            clean = path.lstrip("./")
            if clean.startswith("src/") or clean.startswith("modal/") or clean.startswith("demo/") or clean.startswith("tests/"):
                target = clean
            else:
                target = f"docs/{clean}"
            return f"](https://github.com/raphaelmansuy/edgepii/blob/main/{target}{suffix})"
        return match.group(0)

    markdown = _IMAGE.sub(fix_image, markdown)
    return _LINK.sub(fix_link, markdown)
