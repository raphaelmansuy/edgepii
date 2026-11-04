"""Slice check. A failed hit is dropped. The locator does not search for a repair."""

from __future__ import annotations

from edgepii.protocol import Hit


def slice_text(source: str, hit: Hit) -> str | None:
    if hit.start < 0 or hit.end <= hit.start or hit.end > len(source):
        return None
    text = source[hit.start : hit.end]
    if hit.claimed_text is not None and hit.claimed_text != text:
        return None
    return text
