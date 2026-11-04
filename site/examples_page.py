"""Render the worked-examples page from the recorded library output.

The page must not contain a span a human typed by hand. Every row here comes
from `data/examples.json`, which `gen_data.py` wrote by calling the real library.
A wrong number in a tutorial is worse than no tutorial, so the generator also
asserts the slice invariant on every row before it writes anything.
"""

from __future__ import annotations

import html
import re

TYPE_NOTE = {
    "SECRET": ("secret", "Masked irreversibly. Never enters the vault."),
    "GOV_ID": ("gov_id", "A national id or tax id. No pattern ships in v1 without policy."),
    "PAYMENT": ("payment", "A card after Luhn, or an IBAN after MOD-97."),
    "EMAIL": ("contact", "An RFC 5321 shape. Score is null because no validator exists."),
    "PHONE": ("contact", "libphonenumber decided. A valid number scores 1.0."),
    "IP_ADDRESS": ("contact", "An RFC 4291 or 3986 shape, then a stdlib parse. Score 1.0."),
    "USERNAME": ("contact", "A login name, not a display name."),
    "PERSON": ("person", "A given name, a surname, or a full name."),
    "ADDRESS": ("person", "Street through locality."),
    "DATE_OF_BIRTH": ("quasi", "A birth date. Off by default."),
    "ORG": ("quasi", "An organisation. Off by default."),
}


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def inline(text: str) -> str:
    """Escape, then turn `backticks` into code, so a note can name a token."""

    escaped = esc(text)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)


# A type only a model can find. An example that names one must use a model lane,
# otherwise the block shows an empty result and teaches the wrong lesson.
MODEL_ONLY = {"PERSON", "ADDRESS", "USERNAME", "GOV_ID", "DATE_OF_BIRTH", "ORG"}


def lane_for(row: dict, available: list[str]) -> str:
    """Pick the lane that can actually show the tagged types."""

    model = "en-closed" if "en-closed" in available else None
    needs_model = bool(set(row["tags"]) & MODEL_ONLY)
    if needs_model and model:
        return model
    return "rules" if "rules" in available else available[0]


def score_cell(score) -> str:
    return "—" if score is None else f"{score:.2f}"


def highlight(text: str, spans: list[dict]) -> str:
    parts: list[str] = []
    cursor = 0
    for span in sorted(spans, key=lambda row: row["start"]):
        if span["start"] < cursor:
            continue
        parts.append(esc(text[cursor : span["start"]]))
        parts.append(
            f'<mark class="m" data-class="{esc(span["class"])}" '
            f'title="{esc(span["type"])} {span["start"]}:{span["end"]} · {score_cell(span["score"])}">'
            f'{esc(text[span["start"] : span["end"]])}</mark>'
        )
        cursor = span["end"]
    parts.append(esc(text[cursor:]))
    return "".join(parts)


def span_table(spans: list[dict], text: str) -> str:
    if not spans:
        return (
            '<p class="empty">No span. Nothing in this text matched a grammar on this lane, '
            "and that is the correct answer. A locator that invents a span here would be useless.</p>"
        )
    rows = []
    for index, span in enumerate(spans, start=1):
        ok = text[span["start"] : span["end"]] == span["text"]
        mark = '<span class="ok-cell">ok</span>' if ok else '<span class="bad-cell">fail</span>'
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f'<td><span class="type-dot" data-class="{esc(span["class"])}"></span> {esc(span["type"])}</td>'
            f"<td>{span['start']}</td><td>{span['end']}</td>"
            f"<td><code>{esc(span['text'])}</code></td>"
            f"<td>{score_cell(span['score'])}</td>"
            f'<td class="num">{mark}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="docs-table compact">'
        "<thead><tr><th>#</th><th>Type</th><th>Start</th><th>End</th><th>Text</th>"
        "<th>Score</th><th>Slice</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def vault_table(vault: list[dict]) -> str:
    if not vault:
        return '<p class="hint">The vault is empty. A secret never enters it, and this text holds none.</p>'
    rows = "".join(
        f"<tr><td><code>{esc(row['placeholder'])}</code></td><td><code>{esc(row['value'])}</code></td></tr>"
        for row in vault
    )
    return (
        '<div class="table-wrap"><table class="docs-table compact">'
        f"<thead><tr><th>Placeholder</th><th>Value</th></tr></thead><tbody>{rows}</tbody></table></div>"
    )


def example_block(index: int, row: dict, lane_name: str) -> str:
    lane = row["lanes"][lane_name]
    spans = lane["spans"]
    classes: dict[str, int] = {}
    for span in spans:
        classes[span["type"]] = classes.get(span["type"], 0) + 1
    kinds = ", ".join(f"{count} × {name}" for name, count in sorted(classes.items())) or "no span"

    return f"""<section class="panel-block worked" id="{esc(row['id'])}">
  <div class="block-head">
    <h2><span class="worked-num">{index}</span> {esc(row['title'])}</h2>
    <p class="hint">Lane <code>{esc(lane_name)}</code> · {esc(kinds)}</p>
  </div>
  <p class="example-why">{inline(row['why'])}</p>
  <p class="label">Source</p>
  <div class="highlight">{highlight(row['text'], spans)}</div>
  <p class="label" style="margin-top:18px">Result</p>
  {span_table(spans, row['text'])}
  <div class="split" style="margin-top:20px">
    <div>
      <p class="label">Masked output</p>
      <pre class="masked">{esc(lane['masked'])}</pre>
    </div>
    <div>
      <p class="label">Vault</p>
      {vault_table(lane['vault'])}
    </div>
  </div>
</section>"""


def verify(data: dict) -> None:
    """Every recorded span must satisfy the contract. Fail the build, not the page."""

    problems = []
    for row in data["examples"]:
        for lane_name, lane in row["lanes"].items():
            for span in lane["spans"]:
                slice_ = row["text"][span["start"] : span["end"]]
                if slice_ != span["text"]:
                    problems.append(f"{row['id']}/{lane_name} {span['type']} {span['start']}:{span['end']}")
            spans = sorted(lane["spans"], key=lambda item: item["start"])
            for left, right in zip(spans, spans[1:]):
                if right["start"] < left["end"]:
                    problems.append(f"{row['id']}/{lane_name} overlap {left['type']} {right['type']}")
    if problems:
        raise SystemExit("recorded data breaks the span contract:\n  " + "\n  ".join(problems))


def build(data: dict) -> str:
    verify(data)
    lanes = [row["name"] for row in data["lanes"]]
    primary = "en-closed" if "en-closed" in lanes else "rules"
    rules = "rules" if "rules" in lanes else primary

    cards = []
    for index, row in enumerate(data["examples"], start=1):
        cards.append(example_block(index, row, lane_for(row, lanes)))

    return f"""
<article class="prose">
<h1>Fifteen worked examples</h1>
<p class="lede">
Every span below came from the real library. The page is generated by
<code>site/gen_data.py</code> and <code>site/build.py</code>, and the build fails if a single
recorded offset breaks <code>source[start:end] == text</code>. There is no hand-written result on this
page.
</p>

<div class="callout callout-note">
  <span class="callout-kind">note</span>
  <div class="callout-body">
    Every string is fake. Do not replace one with production text. Examples 10 to 14 need a model lane,
    because a name, an address, a national id, and a login name have no grammar a rule can own.
  </div>
</div>

<h2>How to read a block</h2>
<div class="table-wrap"><table class="docs-table">
<thead><tr><th>Field</th><th>Meaning</th></tr></thead>
<tbody>
<tr><td><strong>Source</strong></td><td>Your string, with each span marked. Hover a mark for its offsets.</td></tr>
<tr><td><strong>Result</strong></td><td>The span table. <code>ok</code> means the recorded slice equals the recorded text.</td></tr>
<tr><td><strong>Score</strong></td><td><code>1.00</code> means a checksum confirmed the slice. <code>—</code> means no validator exists for that form.</td></tr>
<tr><td><strong>Masked</strong></td><td>The same string with placeholders in place of spans.</td></tr>
<tr><td><strong>Vault</strong></td><td>Placeholder to original slice. A secret never appears here.</td></tr>
</tbody>
</table></div>
</article>

{''.join(cards)}

<article class="prose">
<h2>What these examples do not prove</h2>
<p>
An example shows that one string works. It does not measure accuracy. A library can pass every
string on this page and still score badly on a new domain, and that is exactly what the
<a href="../evaluation/">public score</a> found: the closed encoder's person score falls from 0.995
in domain to 0.048 on finance text.
</p>
<p>
Use these pages to understand the shape of a result. Use the
<a href="../guide-evaluate/">evaluation guide</a> to decide whether the library is good enough for
your text.
</p>
</article>
"""
