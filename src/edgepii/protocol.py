"""Private detector hit. check.py is the only module that turns a Hit into a Span."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Hit:
    raw_label: str
    start: int
    end: int
    score: float | None
    detector_id: str
    claimed_text: str | None = None


class Detector(Protocol):
    max_chars: int
    overlap_chars: int

    def locate(self, source: str, labels: list[str]) -> tuple[Hit, ...] | list:
        """Return hits whose offsets are indexes into source."""


def coerce_hit(item: Hit | dict, default_detector: str = "test") -> Hit:
    if isinstance(item, Hit):
        return item
    raw = item.get("raw_label") or item.get("type") or ""
    score = item.get("score")
    return Hit(
        raw_label=str(raw),
        start=int(item["start"]),
        end=int(item["end"]),
        score=None if score is None else float(score),
        detector_id=str(item.get("detector_id") or default_detector),
        claimed_text=item.get("text"),
    )
