"""Split a long source string and shift hit offsets back onto that string.

The split keeps one invariant: every window starts after the previous window
start, and no window is longer than max_chars. A cut prefers the last paragraph
break that keeps that invariant, then the last space, then a hard cut. There is
no fixed "second half" rule, because that rule has no source.
"""

from __future__ import annotations


def split_windows(
    source: str,
    max_chars: int,
    overlap_chars: int = 64,
) -> list[tuple[int, int]]:
    if max_chars <= 0:
        raise ValueError("max_chars")
    if len(source) <= max_chars:
        return [(0, len(source))]
    overlap = overlap_chars
    if overlap >= max_chars:
        overlap = 0
    windows: list[tuple[int, int]] = []
    start = 0
    while start < len(source):
        hard_end = min(len(source), start + max_chars)
        if hard_end >= len(source):
            windows.append((start, len(source)))
            break
        cut = _find_cut(source, start, hard_end, overlap)
        windows.append((start, cut))
        start = cut - overlap
    return windows


def _find_cut(source: str, start: int, hard_end: int, overlap: int) -> int:
    """Return a cut in (start, hard_end] that lets the next window advance."""

    chunk = source[start:hard_end]
    paragraph = chunk.rfind("\n\n")
    if paragraph != -1:
        cut = start + paragraph + 2
        if cut - overlap > start:
            return cut
    space = chunk.rfind(" ")
    if space != -1:
        cut = start + space + 1
        if cut - overlap > start:
            return cut
    return hard_end
