"""Convert spans to the Presidio recognizer-result shape. Core does not import Presidio."""

from __future__ import annotations

from edgepii.span import Span


def to_presidio(spans: tuple[Span, ...] | list[Span]) -> list[dict]:
    return [
        {
            "entity_type": span.type,
            "start": span.start,
            "end": span.end,
            "score": 0.0 if span.score is None else span.score,
        }
        for span in spans
    ]
