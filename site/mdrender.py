"""A small Markdown renderer for the project docs.

The repository docs are the source of truth. The site must not keep a second
copy of them. This module turns the same files into HTML, so a doc edit shows up
on the site without a second edit.

It is deliberately narrow. It reads the constructs that these docs use:

- ATX headings, with a generated id
- paragraphs, bold, inline code, links, italics
- fenced code blocks, tagged with pygments
- pipe tables with an alignment row
- bullet and ordered lists, one level
- block quotes
- horizontal rules
- GitHub-style alerts: `> [!NOTE]` and friends
- the HTML comments that mark a prose register (`<!-- ste: procedural -->`)
"""

from __future__ import annotations

import html
import re

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^```(\w*)\s*$")
_HR = re.compile(r"^-{3,}$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$")
_UL = re.compile(r"^[-*]\s+(.*)$")
_OL = re.compile(r"^(\d+)\.\s+(.*)$")
_COMMENT = re.compile(r"^<!--.*-->$")
_ALERT = re.compile(r"^>\s*\[!(\w+)\]\s*(.*)$")


def code_css() -> str:
    """One stylesheet for every highlighted block on the page."""

    return HtmlFormatter(style="github-dark").get_style_defs(".code pre")


def slugify(text: str) -> str:
    plain = re.sub(r"<[^>]+>", "", text)
    plain = re.sub(r"`", "", plain)
    plain = re.sub(r"[^\w\s-]", "", plain, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_]+", "-", plain) or "section"


def headings(markdown: str) -> list[tuple[int, str, str]]:
    """Return (level, id, text) for a table of contents."""

    found: list[tuple[int, str, str]] = []
    in_fence = False
    for line in markdown.splitlines():
        if _FENCE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if not match:
            continue
        level = len(match.group(1))
        text = _inline(match.group(2).strip())
        found.append((level, slugify(text), _strip_tags(text)))
    return found


def render(markdown: str, shift: int = 0) -> str:
    """Render Markdown to HTML fragments. `shift` demotes headings under a page h1."""

    lines = markdown.splitlines()
    out: list[str] = []
    index = 0
    # A `ste:` marker is a note to the writer, not content.
    while index < len(lines) and (_COMMENT.match(lines[index].strip()) or not lines[index].strip()):
        index += 1
        if index > 6:
            break
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped == "":
            index += 1
            continue

        if _COMMENT.match(stripped):
            index += 1
            continue

        fence = _FENCE.match(stripped)
        if fence:
            language = fence.group(1) or "text"
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            out.append(_code("\n".join(block), language))
            continue

        heading = _HEADING.match(line)
        if heading:
            level = min(6, len(heading.group(1)) + shift)
            text = _inline(heading.group(2).strip())
            out.append(f'<h{level} id="{slugify(text)}">{text}</h{level}>')
            index += 1
            continue

        if _HR.match(stripped):
            out.append("<hr />")
            index += 1
            continue

        alert = _ALERT.match(stripped)
        if alert:
            kind = alert.group(1).lower()
            body: list[str] = []
            first = alert.group(2).strip()
            if first:
                body.append(_inline(first))
            index += 1
            while index < len(lines) and lines[index].strip().startswith(">"):
                body.append(_inline(lines[index].strip().lstrip(">").strip()))
                index += 1
            out.append(
                f'<div class="callout callout-{kind}">'
                f'<span class="callout-kind">{html.escape(kind)}</span>'
                f'<div class="callout-body">{"<br />".join(row for row in body if row)}</div>'
                "</div>"
            )
            continue

        if stripped.startswith(">"):
            body = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                body.append(_inline(lines[index].strip().lstrip(">").strip()))
                index += 1
            out.append(f'<blockquote><p>{" ".join(row for row in body if row)}</p></blockquote>')
            continue

        if stripped.startswith("|"):
            block = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index].strip())
                index += 1
            out.append(_table(block))
            continue

        if _UL.match(stripped) or _OL.match(stripped):
            ordered = bool(_OL.match(stripped))
            pattern = _OL if ordered else _UL
            items: list[str] = []
            while index < len(lines):
                candidate = lines[index].strip()
                match = pattern.match(candidate)
                if not match:
                    if candidate and items and not candidate.startswith(("|", "#", ">", "```")):
                        # A wrapped continuation line belongs to the last item.
                        items[-1] = items[-1] + " " + _inline(candidate)
                        index += 1
                        continue
                    break
                items.append(_inline(match.group(match.lastindex)))
                index += 1
            tag = "ol" if ordered else "ul"
            body = "".join(f"<li>{item}</li>" for item in items)
            out.append(f'<{tag} class="doc-list">{body}</{tag}>')
            continue

        paragraph = []
        while index < len(lines):
            candidate = lines[index]
            if not candidate.strip():
                break
            if _HEADING.match(candidate) or _FENCE.match(candidate.strip()):
                break
            if candidate.strip().startswith(("|", ">")) or _UL.match(candidate.strip()) or _OL.match(candidate.strip()):
                break
            paragraph.append(_inline(candidate.strip()))
            index += 1
        if paragraph:
            out.append(f"<p>{' '.join(paragraph)}</p>")
        else:
            index += 1
    return "\n".join(out)


def _code(block: str, language: str) -> str:
    if language == "mermaid":
        # Keep the source visible as a fallback. `site.js` upgrades this to a
        # drawn diagram when the mermaid module loads, and leaves the text alone
        # when it does not, so an offline reader still sees the structure.
        return (
            '<div class="diagram" data-mermaid>'
            '<div class="code-head"><span class="code-lang">diagram</span>'
            '<button type="button" class="code-copy" data-copy-code aria-label="Copy diagram source">Copy</button></div>'
            f'<pre class="diagram-source"><code>{html.escape(block)}</code></pre>'
            "</div>"
        )
    try:
        lexer = get_lexer_by_name(language, stripnl=False)
        body = highlight(block, lexer, HtmlFormatter(nowrap=True))
    except Exception:  # noqa: BLE001 - an unknown language is plain text
        body = html.escape(block)
    label = html.escape(language)
    return (
        '<div class="code">'
        f'<div class="code-head"><span class="code-lang">{label}</span>'
        f'<button type="button" class="code-copy" data-copy-code aria-label="Copy code">Copy</button></div>'
        f"<pre><code>{body}</code></pre>"
        "</div>"
    )


def _table(block: list[str]) -> str:
    rows = [_split_row(row) for row in block]
    aligns: list[str] = []
    if len(rows) > 1 and _TABLE_SEP.match(block[1]):
        aligns = [_alignment(cell) for cell in rows[1]]
        rows = [rows[0]] + rows[2:]
    if not rows:
        return ""
    head = rows[0]
    body = rows[1:]
    cells = "".join(f'<th style="text-align:{_align(aligns, i)}">{_inline(cell)}</th>' for i, cell in enumerate(head))
    out = ['<div class="table-wrap"><table class="doc-table">', f"<thead><tr>{cells}</tr></thead>", "<tbody>"]
    for row in body:
        cells = "".join(
            f'<td style="text-align:{_align(aligns, i)}">{_inline(cell)}</td>' for i, cell in enumerate(row)
        )
        out.append(f"<tr>{cells}</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def _split_row(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    # Keep a pipe inside a code span, so `a | b` survives.
    parts: list[str] = []
    depth = 0
    current = ""
    for char in row:
        if char == "`":
            depth = 1 - depth
        if char == "|" and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    parts.append(current.strip())
    return parts


def _alignment(cell: str) -> str:
    cell = cell.strip()
    if cell.startswith(":") and cell.endswith(":"):
        return "center"
    if cell.endswith(":"):
        return "right"
    return "left"


def _align(aligns: list[str], index: int) -> str:
    if index < len(aligns):
        return aligns[index]
    return "left"


def _inline(text: str) -> str:
    """Inline Markdown to HTML, with code spans protected from the other passes."""

    placeholders: dict[str, str] = {}

    def stash(match: re.Match[str]) -> str:
        key = f"\x00{len(placeholders)}\x00"
        placeholders[key] = f"<code>{html.escape(match.group(1))}</code>"
        return key

    text = re.sub(r"`([^`]+)`", stash, text)

    def stash_link(match: re.Match[str]) -> str:
        key = f"\x00{len(placeholders)}\x00"
        label = match.group(1)
        href = match.group(2)
        external = href.startswith(("http://", "https://"))
        attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
        placeholders[key] = f'<a href="{html.escape(href, quote=True)}"{attrs}>{label}</a>'
        return key

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", stash_link, text)
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    for key, value in placeholders.items():
        text = text.replace(html.escape(key), value)
    return text


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))
