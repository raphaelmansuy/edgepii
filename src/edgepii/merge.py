"""One non-overlapping span list. This is the only overlap policy."""

from __future__ import annotations

from edgepii.labelmap import Taxonomy
from edgepii.span import Span


def _overlaps(left: Span, right: Span) -> bool:
    """Half-open test. Kept for the tests that pin the old policy shape."""

    return left.start < right.end and right.start < left.end


def _prefer_match(span: Span, taxonomy: Taxonomy) -> int:
    info = taxonomy.types[span.type]
    is_rule = span.detector_id.startswith("rules.")
    if info.prefer == "rule":
        return 1 if is_rule else 0
    if info.prefer == "model":
        return 1 if not is_rule else 0
    return 0


def _better(left: Span, right: Span, taxonomy: Taxonomy) -> Span:
    left_key = (
        taxonomy.types[left.type].rank,
        _prefer_match(left, taxonomy),
        left.end - left.start,
        left.score if left.score is not None else -1.0,
        -left.start,
    )
    right_key = (
        taxonomy.types[right.type].rank,
        _prefer_match(right, taxonomy),
        right.end - right.start,
        right.score if right.score is not None else -1.0,
        -right.start,
    )
    if left_key != right_key:
        return left if left_key > right_key else right
    return left if left.type <= right.type else right


def merge_spans(
    spans: list[Span],
    taxonomy: Taxonomy,
    allowed_types: set[str],
    min_score: float | None = None,
    drop_unscored: bool = False,
) -> list[Span]:
    """Return one non-overlapping list. min_score is caller policy, not a default.

    The library ships no minimum score. Any constant here would be an
    unmeasured guess. A caller that wants one passes a number that the caller
    measured on its own data.

    A span with no score is the case that matters for a redaction tool. A rule
    that confirms a slice through a grammar reports `None`, because no
    probability exists for it. Dropping such a span because a floor cannot
    compare against it would send an email or a phone number to the model in
    the clear, which is the failure this library exists to prevent. So a span
    with no score **survives** a floor by default.

    Pass `drop_unscored=True` to get the older behaviour, where a floor also
    removes every span that has no score. A caller should only do that after
    measuring what it costs.

    Overlap resolution is a sweep, not a pairwise compare. The list is sorted by
    start offset, so once a later span starts at or after the current span ends,
    no later span can overlap it. That bound keeps a long document linear in the
    number of spans instead of quadratic.
    """

    kept: list[Span] = []
    for span in spans:
        if span.type not in allowed_types:
            continue
        if taxonomy.types.get(span.type) is None:
            continue
        if min_score is not None:
            if span.score is None:
                # No measured confidence. Keep it unless the caller opted out,
                # because dropping it leaves the value unmasked.
                if drop_unscored:
                    continue
            elif span.score < min_score:
                continue
        kept.append(span)
    if not kept:
        return []

    kept.sort(key=lambda span: (span.start, span.end, span.type))
    winners = _resolve_overlaps(kept, taxonomy)
    winners.sort(key=lambda span: (span.start, span.end, span.type))
    return winners


def _resolve_overlaps(ordered: list[Span], taxonomy: Taxonomy) -> list[Span]:
    """Group transitively overlapping spans, then keep one winner per group.

    `ordered` is sorted by start offset. A group is closed as soon as a span
    starts at or after the furthest end seen so far, because nothing later can
    reach back into it.
    """

    winners: list[Span] = []
    group: list[Span] = []
    reach = -1

    for span in ordered:
        if group and span.start >= reach:
            winners.append(_better_of(group, taxonomy))
            group = []
            reach = -1
        group.append(span)
        reach = max(reach, span.end)

    if group:
        winners.append(_better_of(group, taxonomy))
    return winners


def _better_of(group: list[Span], taxonomy: Taxonomy) -> Span:
    winner = group[0]
    for span in group[1:]:
        winner = _better(winner, span, taxonomy)
    return winner
