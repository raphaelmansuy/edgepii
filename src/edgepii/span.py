"""Public span types. A log of to_dict copies PII because it includes text."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Span:
    """One half-open character range on the source string."""

    type: str
    start: int
    end: int
    text: str
    score: float | None
    detector_id: str
    raw_label: str


@dataclass(frozen=True, slots=True)
class LocateResult:
    """Spans for one source string. text fields are slices of that string."""

    taxonomy_version: str
    spans: tuple[Span, ...]
    dropped: int
    preset: str
    revision: str

    def to_dict(self) -> dict:
        """Export the contract. Callers who log this dict copy PII."""

        return {
            "taxonomy_version": self.taxonomy_version,
            "preset": self.preset,
            "revision": self.revision,
            "dropped": self.dropped,
            "spans": [
                {
                    "type": span.type,
                    "start": span.start,
                    "end": span.end,
                    "text": span.text,
                    "score": span.score,
                    "detector_id": span.detector_id,
                    "raw_label": span.raw_label,
                }
                for span in self.spans
            ],
        }
