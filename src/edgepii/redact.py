"""Replace spans with placeholders. The caller holds the vault. This function keeps nothing."""

from __future__ import annotations

from edgepii.errors import OverlapError, UnknownType
from edgepii.labelmap import Taxonomy, load_taxonomy
from edgepii.span import Span


def redact(
    source: str,
    spans: tuple[Span, ...] | list[Span],
    taxonomy: str | Taxonomy = "2026.11",
) -> tuple[str, dict[str, str]]:
    loaded = taxonomy if isinstance(taxonomy, Taxonomy) else load_taxonomy(taxonomy)
    ordered = tuple(sorted(spans, key=lambda span: (span.start, span.end, span.type)))
    _reject_overlaps(ordered)
    placeholders = _assign_placeholders(ordered, loaded)
    masked = source
    for span, token in sorted(
        zip(ordered, placeholders, strict=True),
        key=lambda pair: pair[0].start,
        reverse=True,
    ):
        masked = masked[: span.start] + token + masked[span.end :]
    vault: dict[str, str] = {}
    for span, token in zip(ordered, placeholders, strict=True):
        if loaded.require(span.type).redact == "irreversible":
            continue
        vault.setdefault(token, span.text)
    return masked, vault


def _reject_overlaps(spans: tuple[Span, ...]) -> None:
    for index, left in enumerate(spans):
        for right in spans[index + 1 :]:
            if left.start < right.end and right.start < left.end:
                raise OverlapError(left.start, left.end)


def _assign_placeholders(spans: tuple[Span, ...], taxonomy: Taxonomy) -> list[str]:
    counts: dict[str, int] = {}
    seen: dict[tuple[str, str], str] = {}
    tokens: list[str] = []
    for span in spans:
        info = taxonomy.types.get(span.type)
        if info is None:
            raise UnknownType(span.type)
        if info.redact == "irreversible":
            tokens.append("<SECRET>")
            continue
        key = (span.type, span.text)
        token = seen.get(key)
        if token is None:
            counts[span.type] = counts.get(span.type, 0) + 1
            token = f"<{span.type}_{counts[span.type]}>"
            seen[key] = token
        tokens.append(token)
    return tokens
