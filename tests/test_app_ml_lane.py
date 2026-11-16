"""Tests for the ML lane: the GLiNER classifier served by Databricks.

The endpoint itself is not called here. What is tested is the contract the app
owns: the label fold, the slice check that drops a bad offset, the error
messages, and the merging of two lanes through the library's own policy.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "apps" / "edgepii-databricks"
sys.path.insert(0, str(APP_DIR))

import ml_lane  # noqa: E402
import pipeline  # noqa: E402
from edgepii.span import Span  # noqa: E402

SOURCE = "Ada Lovelace called from +852 5555 0101. Email ada@example.com."


def _span(label: str, text: str, source: str = SOURCE, score: float = 0.9) -> dict:
    start = source.index(text)
    return {
        "label": label,
        "raw_label": label.lower(),
        "start": start,
        "end": start + len(text),
        "text": text,
        "score": score,
    }


def _stub_response(monkeypatch, spans: list[dict], status_code: int = 200, body=None):
    class Response:
        def __init__(self):
            self.status_code = status_code
            self.text = "stub"

        def json(self):
            # The real envelope: a one-column DataFrame nests one level.
            return body if body is not None else {"predictions": [{"predictions": spans}]}

    monkeypatch.setattr(ml_lane.httpx, "post", lambda *a, **k: Response())


def test_spans_that_fail_the_slice_check_are_dropped(monkeypatch):
    """A remote model is exactly where a bad offset would come from."""

    # Claim a range whose slice is not the text the model says it found.
    bad = {
        "label": "EMAIL",
        "raw_label": "email",
        "start": 0,
        "end": 12,
        "text": "ada@example.com",  # SOURCE[0:12] == "Ada Lovelace"
        "score": 0.9,
    }
    good = _span("PHONE", "+852 5555 0101")
    _stub_response(monkeypatch, [bad, good])

    spans = ml_lane.locate(
        SOURCE, host="https://x", endpoint="ep", headers={"Authorization": "Bearer t"}
    )

    assert [span.type for span in spans] == ["PHONE"]
    assert all(SOURCE[s.start : s.end] == s.text for s in spans)


def test_an_out_of_range_offset_is_dropped(monkeypatch):
    bad = _span("EMAIL", "ada@example.com")
    bad["end"] = len(SOURCE) + 50
    _stub_response(monkeypatch, [bad])

    spans = ml_lane.locate(
        SOURCE, host="https://x", endpoint="ep", headers={"Authorization": "Bearer t"}
    )
    assert spans == []


def test_a_label_outside_the_fold_is_dropped(monkeypatch):
    """The model answers in words; only words the taxonomy has a policy for count."""

    _stub_response(
        monkeypatch,
        [
            {**_span("PERSON", "Ada Lovelace"), "label": "PERSON"},
            {**_span("MOON_PHASE", "called"), "label": "MOON_PHASE"},
        ],
    )

    spans = ml_lane.locate(
        SOURCE, host="https://x", endpoint="ep", headers={"Authorization": "Bearer t"}
    )
    assert [span.type for span in spans] == ["PERSON"]


def test_a_403_names_the_endpoint_grant(monkeypatch):
    _stub_response(monkeypatch, [], status_code=403)

    with pytest.raises(ml_lane.MlLaneError) as caught:
        ml_lane.locate(
            SOURCE, host="https://x", endpoint="ep", headers={"Authorization": "Bearer t"}
        )
    assert caught.value.kind == "forbidden"
    assert "CAN_QUERY" in caught.value.message


def test_a_record_response_is_reported_not_iterated(monkeypatch):
    """A pyfunc that returns columns rather than a span list must say so."""

    _stub_response(monkeypatch, [], body={"predictions": [{"predictions": [{"label": "PERSON", "score": 0.9}]}]})

    with pytest.raises(ml_lane.MlLaneError) as caught:
        ml_lane.locate(
            SOURCE, host="https://x", endpoint="ep", headers={"Authorization": "Bearer t"}
        )
    assert caught.value.kind == "serving"
    assert "signature" in caught.value.message


def test_too_long_source_is_a_caller_error(monkeypatch):
    with pytest.raises(ml_lane.MlLaneError) as caught:
        ml_lane.locate(
            "x" * (ml_lane.MAX_CHARS + 1),
            host="https://x",
            endpoint="ep",
            headers={},
        )
    assert caught.value.kind == "too_long"


def test_empty_source_makes_no_call(monkeypatch):
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("no request should be made for empty text")

    monkeypatch.setattr(ml_lane.httpx, "post", boom)
    assert ml_lane.locate("", host="https://x", endpoint="ep", headers={}) == []
    assert called["n"] == 0


def test_the_rules_lane_is_offered_without_an_endpoint(monkeypatch):
    monkeypatch.delenv("EDGEPII_ML_ENDPOINT", raising=False)
    names = [row["name"] for row in pipeline.lanes()]
    assert names == ["rules"]


def test_an_endpoint_adds_the_ml_and_hybrid_lanes(monkeypatch):
    monkeypatch.setenv("EDGEPII_ML_ENDPOINT", "edgepii-pii-ml")
    monkeypatch.setenv("EDGEPII_ML_WITH_RULES", "1")
    names = [row["name"] for row in pipeline.lanes()]
    assert names == ["rules", "ml", "hybrid"]


def test_ml_without_the_rules_union_offers_two_lanes(monkeypatch):
    monkeypatch.setenv("EDGEPII_ML_ENDPOINT", "edgepii-pii-ml")
    monkeypatch.setenv("EDGEPII_ML_WITH_RULES", "0")
    names = [row["name"] for row in pipeline.lanes()]
    assert names == ["rules", "ml"]


def test_an_unknown_lane_is_refused_before_any_network_call(monkeypatch):
    monkeypatch.setenv("EDGEPII_MODELS", "databricks-gpt-oss-20b")
    monkeypatch.delenv("EDGEPII_ML_ENDPOINT", raising=False)

    with pytest.raises(pipeline.PipelineError) as caught:
        pipeline.run(SOURCE, model="databricks-gpt-oss-20b", lane="ml")
    assert caught.value.kind == "bad_lane"
    assert "rules" in caught.value.message


def test_hybrid_merges_both_lanes_through_the_library_policy(monkeypatch):
    """A rule span must win where the taxonomy marks `prefer: rule`.

    Email is `prefer: rule`, so a model span covering the same characters must
    lose to the rule span even when the model is more confident.
    """

    monkeypatch.setenv("EDGEPII_MODELS", "databricks-gpt-oss-20b")
    monkeypatch.setenv("EDGEPII_ML_ENDPOINT", "edgepii-pii-ml")

    model_spans = [
        Span(
            type="EMAIL",
            start=SOURCE.index("ada@example.com"),
            end=SOURCE.index("ada@example.com") + len("ada@example.com"),
            text="ada@example.com",
            score=0.99,
            detector_id="serving.edgepii-pii-ml",
            raw_label="email",
        ),
        Span(
            type="PERSON",
            start=SOURCE.index("Ada Lovelace"),
            end=SOURCE.index("Ada Lovelace") + len("Ada Lovelace"),
            text="Ada Lovelace",
            score=0.98,
            detector_id="serving.edgepii-pii-ml",
            raw_label="person",
        ),
    ]

    def fake_ml(source, headers):
        return model_spans, {"ml_ms": 5.0}

    monkeypatch.setattr(pipeline, "_ml_spans", fake_ml)
    monkeypatch.setattr(pipeline, "_headers_or_raise", lambda: {})

    result, timing = pipeline._detect(SOURCE, "rules", "hybrid")

    by_type = {span.type: span for span in result.spans}
    assert "PERSON" in by_type, "the ML lane must contribute a name"
    assert by_type["PERSON"].detector_id.startswith("serving.")
    # The rules lane also finds the email; only one email span may survive.
    emails = [span for span in result.spans if span.type == "EMAIL"]
    assert len(emails) == 1
    assert timing["ml_ms"] == 5.0


def test_every_merged_span_still_proves_the_slice(monkeypatch):
    monkeypatch.setenv("EDGEPII_ML_ENDPOINT", "edgepii-pii-ml")
    model_spans = [
        Span(
            type="PERSON",
            start=0,
            end=len("Ada Lovelace"),
            text="Ada Lovelace",
            score=0.95,
            detector_id="serving.edgepii-pii-ml",
            raw_label="person",
        )
    ]
    monkeypatch.setattr(pipeline, "_ml_spans", lambda source, headers: (model_spans, {"ml_ms": 1.0}))
    monkeypatch.setattr(pipeline, "_headers_or_raise", lambda: {})

    result, _ = pipeline._detect(SOURCE, "rules", "hybrid")

    assert result.spans
    for span in result.spans:
        assert SOURCE[span.start : span.end] == span.text


def test_the_ml_lane_alone_returns_only_model_spans(monkeypatch):
    monkeypatch.setenv("EDGEPII_ML_ENDPOINT", "edgepii-pii-ml")
    model_spans = [
        Span(
            type="PERSON",
            start=0,
            end=len("Ada Lovelace"),
            text="Ada Lovelace",
            score=0.95,
            detector_id="serving.edgepii-pii-ml",
            raw_label="person",
        )
    ]
    monkeypatch.setattr(pipeline, "_ml_spans", lambda source, headers: (model_spans, {"ml_ms": 2.0}))
    monkeypatch.setattr(pipeline, "_headers_or_raise", lambda: {})

    result, timing = pipeline._detect(SOURCE, "rules", "ml")

    assert [span.type for span in result.spans] == ["PERSON"]
    assert result.preset.endswith("+ml")
    assert timing["ml_ms"] == 2.0


def test_the_real_two_level_envelope_is_parsed(monkeypatch):
    """The live endpoint nests a DataFrame row one level deep.

    This exact payload was captured from `edgepii-pii-ml` after it went READY.
    Pinning it means a future MLflow change to the envelope fails here rather
    than in the deployed demo.
    """

    captured = {
        "predictions": [
            {
                "predictions": [
                    {
                        "label": "PERSON",
                        "raw_label": "person",
                        "start": 0,
                        "end": 12,
                        "text": "Ada Lovelace",
                        "score": 0.991481,
                    },
                    {
                        "label": "PHONE",
                        "raw_label": "phone number",
                        "start": 25,
                        "end": 39,
                        "text": "+852 5555 0101",
                        "score": 0.999993,
                    },
                    {
                        "label": "EMAIL",
                        "raw_label": "email",
                        "start": 47,
                        "end": 62,
                        "text": "ada@example.com",
                        "score": 0.999986,
                    },
                ]
            }
        ]
    }
    _stub_response(monkeypatch, [], body=captured)

    spans = ml_lane.locate(
        SOURCE, host="https://x", endpoint="ep", headers={"Authorization": "Bearer t"}
    )

    assert [span.type for span in spans] == ["PERSON", "PHONE", "EMAIL"]
    assert spans[0].text == "Ada Lovelace"
    assert spans[0].score > 0.99
    for span in spans:
        assert SOURCE[span.start : span.end] == span.text
