"""Character containment on original offsets; never scores overlapping chars twice."""

from __future__ import annotations


def union_ranges(rows) -> list[tuple[int, int]]:
    merged = []
    for start, end in sorted((int(a), int(b)) for a, b in rows if b > a):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def covered(start: int, end: int, masks: list[tuple[int, int]]) -> bool:
    return any(lo <= start and hi >= end for lo, hi in masks)


def character_counts(gold, predictions) -> tuple[int, int, int]:
    truth = union_ranges((row[1], row[2]) for row in gold)
    masks = union_ranges((row[1], row[2]) for row in predictions)
    overlap = 0
    left = right = 0
    while left < len(truth) and right < len(masks):
        a, b = truth[left]
        c, d = masks[right]
        overlap += max(0, min(b, d) - max(a, c))
        if b <= d:
            left += 1
        else:
            right += 1
    return sum(b-a for a,b in truth), sum(b-a for a,b in masks), overlap
