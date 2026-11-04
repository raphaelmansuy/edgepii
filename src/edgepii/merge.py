"""One non-overlapping span list. This is the only overlap policy."""

from __future__ import annotations

from edgepii.labelmap import Taxonomy
from edgepii.span import Span


def _overlaps(left: Span, right: Span) -> bool:
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
) -> list[Span]:
    """Return one non-overlapping list. min_score is caller policy, not a default.

    The library ships no minimum score. Any constant here would be an
    unmeasured guess. A caller that wants one passes a number that the caller
    measured on its own data.

    A span with no score cannot meet a floor. It has no measured confidence,
    so `min_score` drops it. With no `min_score` it stays, because the caller
    asked for every span.
    """

    kept: list[Span] = []
    for span in spans:
        if span.type not in allowed_types:
            continue
        info = taxonomy.types.get(span.type)
        if info is None:
            continue
        if min_score is not None:
            if span.score is None or span.score < min_score:
                continue
        kept.append(span)
    if not kept:
        return []
    parent = list(range(len(kept)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i, left in enumerate(kept):
        for j in range(i + 1, len(kept)):
            if _overlaps(left, kept[j]):
                root_i = find(i)
                root_j = find(j)
                if root_i != root_j:
                    parent[root_j] = root_i
    groups: dict[int, list[Span]] = {}
    for index, span in enumerate(kept):
        groups.setdefault(find(index), []).append(span)
    winners = [_better_of(group, taxonomy) for group in groups.values()]
    winners.sort(key=lambda span: (span.start, span.end, span.type))
    return winners


def _better_of(group: list[Span], taxonomy: Taxonomy) -> Span:
    winner = group[0]
    for span in group[1:]:
        winner = _better(winner, span, taxonomy)
    return winner
