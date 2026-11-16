"""Tests for the Databricks App pipeline. No network and no serving endpoint.

The four stages are tested apart from each other: detect and mask run for real,
the model call is replaced with a stub, and restore runs on the stub's answer.
That keeps this suite fast and free while still proving the parts the app owns.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "apps" / "edgepii-databricks"
sys.path.insert(0, str(APP_DIR))

import pipeline  # noqa: E402
from pipeline import ModelCall, PipelineError, _segments, _tokens_in  # noqa: E402

TICKET = (
    "Customer called from +852 5555 0101 about order 48291. "
    "Reply to ada@example.com. The card on file is 4242424242424242."
)


@pytest.fixture(autouse=True)
def _stub_model(monkeypatch):
    """Answer with the placeholders the app sent, so restore has work to do."""

    def fake_invoke(model, messages, max_tokens):
        masked = messages[-1]["content"]
        tokens = sorted(_tokens_in(masked))
        body = "I logged the ticket. " + " ".join(f"Seen {token}." for token in tokens)
        return ModelCall(
            content=body,
            reasoning="",
            model=model,
            latency_ms=1.0,
            prompt_tokens=10,
            completion_tokens=5,
        )

    monkeypatch.setattr(pipeline, "_invoke", fake_invoke)
    monkeypatch.setenv("EDGEPII_MODELS", "databricks-gpt-oss-20b")


def test_masked_text_never_contains_the_values():
    payload = pipeline.run(TICKET, model="databricks-gpt-oss-20b")

    assert payload["ok"] is True
    assert "ada@example.com" not in payload["masked"]
    assert "4242424242424242" not in payload["masked"]
    assert "48291" in payload["masked"], "an order id is not PII"


def test_every_span_proves_the_slice_contract():
    payload = pipeline.run(TICKET, model="databricks-gpt-oss-20b")

    assert payload["spans"]
    assert payload["slice_ok"] is True
    for span in payload["spans"]:
        assert payload["source"][span["start"] : span["end"]] == span["text"]


def test_restore_puts_the_values_back():
    payload = pipeline.run(TICKET, model="databricks-gpt-oss-20b")

    assert payload["restore_ok"] is True
    assert "ada@example.com" in payload["answer"]
    assert "4242424242424242" in payload["answer"]
    assert payload["unresolved"] == []


def test_a_secret_stays_sealed_and_is_not_a_failure():
    """<SECRET> is irreversible, so its survival is the intended outcome."""

    source = "The staging password: hunter2 and the host is 203.0.113.10."
    payload = pipeline.run(source, model="databricks-gpt-oss-20b")

    assert "hunter2" not in payload["masked"]
    assert "<SECRET>" not in {row["value"] for row in payload["vault"]}
    assert payload["sealed"] == ["<SECRET>"]
    assert payload["restore_ok"] is True


def test_segments_rebuild_the_restored_answer():
    """The UI highlights segments, so they must concatenate to the answer."""

    from edgepii import restore

    vault = {"<EMAIL_1>": "ada@example.com", "<PHONE_1>": "+1 202 555 0147"}
    raw = "Write to <EMAIL_1> or < email_1 >. Call <PHONE_1>."
    segments = _segments(raw, vault)

    rebuilt = "".join(segment["text"] for segment in segments)
    assert rebuilt == restore(raw, vault).text
    assert rebuilt == "Write to ada@example.com or ada@example.com. Call +1 202 555 0147."
    assert [seg["kind"] for seg in segments].count("value") == 3


def test_a_value_inside_a_longer_token_does_not_double_replace():
    """<EMAIL_1> and <EMAIL_10> share a prefix. Longest must win."""

    vault = {"<EMAIL_1>": "a@example.com", "<EMAIL_10>": "ten@example.com"}
    segments = _segments("One <EMAIL_10>, two <EMAIL_1>.", vault)

    values = [seg["text"] for seg in segments if seg["kind"] == "value"]
    assert values == ["ten@example.com", "a@example.com"]


def test_empty_source_is_a_caller_error():
    with pytest.raises(PipelineError) as caught:
        pipeline.run("   ", model="databricks-gpt-oss-20b")
    assert caught.value.kind == "bad_source"


def test_a_model_outside_the_allow_list_is_refused():
    with pytest.raises(PipelineError) as caught:
        pipeline.run("hi", model="some-other-endpoint")
    assert caught.value.kind == "bad_model"


def test_an_empty_answer_is_reported_not_shown(monkeypatch):
    """A reasoning model can spend the budget and return nothing."""

    monkeypatch.setattr(
        pipeline,
        "_invoke",
        lambda model, messages, max_tokens: ModelCall("", "", model, 1.0, 1, 1),
    )
    with pytest.raises(PipelineError) as caught:
        pipeline.run("Email ada@example.com.", model="databricks-gpt-oss-20b")
    assert caught.value.kind == "empty_answer"
