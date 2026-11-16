"""Render ARCHITECTURE.md into the app, so the diagrams live in the demo too.

The Markdown file is the single source of truth. This module reads it, converts
it to HTML once at import, and rewrites each `mermaid` fence into the same
`data-mermaid` container the repo's docs site uses: the source stays visible as a
fallback, and `static/architecture.js` upgrades it to a drawn diagram when the
Mermaid module loads.

Keeping one source matters. A page that restates the architecture in its own
words drifts from the file the moment either one changes.
"""

from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
DOC = HERE / "ARCHITECTURE.md"

# A fence whose info string is exactly "mermaid". Anything else is ordinary code.
_MERMAID_FENCE = re.compile(
    r'<pre><code class="language-mermaid">(.*?)</code></pre>',
    re.S,
)


def _diagram(source: str) -> str:
    """One diagram block: visible source, plus the hook the script upgrades.

    `markdown_it` escaped the fence body, so `source` arrives as HTML. Escaping
    it again would hand Mermaid a doubly-escaped string, so it is unescaped back
    to the literal Markdown first. The result is byte-identical to the fence in
    ARCHITECTURE.md, which is what Mermaid receives as `textContent`.

    Some labels already spell a bracket as `&lt;SECRET&gt;`, which Mermaid renders
    as `<SECRET>`. That is the source's choice and survives unchanged here.
    """

    escaped = html.escape(html.unescape(source.strip()))
    return (
        '<figure class="diagram" data-mermaid>'
        '<div class="diagram-head"><span>diagram</span>'
        '<button type="button" class="ghost tiny" data-copy-diagram>Copy source</button>'
        "</div>"
        f'<pre class="diagram-source"><code>{escaped}</code></pre>'
        "</figure>"
    )


@lru_cache(maxsize=1)
def rendered() -> str:
    """The architecture document as HTML, with diagrams as upgradeable blocks."""

    if not DOC.exists():  # pragma: no cover - the file ships next to this module
        return "<p>The architecture document is missing from this deployment.</p>"

    text = DOC.read_text(encoding="utf-8")
    body = MarkdownIt("commonmark", {"html": True}).enable("table").render(text)
    return _MERMAID_FENCE.sub(lambda match: _diagram(match.group(1)), body)


@lru_cache(maxsize=1)
def title() -> str:
    """The first heading, without its marker. Falls back to a fixed label."""

    if not DOC.exists():  # pragma: no cover
        return "Architecture"
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Architecture"


def payload() -> dict:
    """What the page needs. `diagrams` lets the UI say what to expect up front."""

    body = rendered()
    return {
        "title": title(),
        "html": body,
        "diagrams": body.count('class="diagram"'),
    }
