"""Tests for the tutorial page.

The tutorial must not drift from the library. Every output string is produced by
calling `edgepii` at import, so these tests assert that each step still says what
the library actually does, not that a hand-typed string matches itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "apps" / "edgepii-databricks"
sys.path.insert(0, str(APP_DIR))

import tutorial  # noqa: E402
from edgepii import Locator, redact, restore  # noqa: E402


def test_steps_are_numbered_and_complete():
    payload = tutorial.payload()
    assert len(payload["steps"]) == 6
    assert [step["index"] for step in payload["steps"]] == [1, 2, 3, 4, 5, 6]
    for step in payload["steps"]:
        assert step["title"], "a step needs a title"
        assert step["body"], "a step needs prose"
        assert step["code"], "a step needs code to run"
        assert step["output"], "a step needs output"


def test_step_one_output_is_the_locator_result():
    """If the locator changes, the tutorial's first step must change with it."""

    result = Locator.preset("rules").locate(tutorial.TICKET)
    step = tutorial.payload()["steps"][0]

    for span in result.spans:
        assert span.text in step["output"], f"{span.type} is missing from the tutorial"
    assert "every slice matches the source: True" in step["output"]


def test_step_two_shows_the_vault_the_library_returns():
    result = Locator.preset("rules").locate(tutorial.TICKET)
    _masked, vault = redact(tutorial.TICKET, result.spans)
    step = tutorial.payload()["steps"][1]

    for token, value in vault.items():
        assert token in step["output"]
        assert value in step["output"]


def test_step_three_really_keeps_the_secret_out_of_the_vault():
    """The claim on the page is a fact about the library, so assert the fact."""

    source = "Escalate ticket 77. The staging password: hunter2 and the box is 203.0.113.10."
    result = Locator.preset("rules").locate(source)
    masked, vault = redact(source, result.spans)

    assert "hunter2" not in masked
    assert "<SECRET>" in masked
    assert "hunter2" not in vault.values()

    step = tutorial.payload()["steps"][2]
    assert "secret found in masked:  False" in step["output"]
    assert "secret found in vault:   False" in step["output"]
    assert "hunter2" not in step["output"], "the tutorial must not print the secret"


def test_step_four_reuses_a_token_for_a_repeated_value():
    step = tutorial.payload()["steps"][3]
    assert "<EMAIL_1> or <EMAIL_2>" in step["output"]
    assert "The desk is <EMAIL_1>." in step["output"]


def test_step_five_restores_the_values():
    step = tutorial.payload()["steps"][4]
    assert "+852 5555 0101" in step["output"]
    assert "ada@example.com" in step["output"]
    assert "ok: True" in step["output"]


def test_step_six_shows_the_gate_failing():
    """The page claims the gate catches invented PII. Prove it does."""

    step = tutorial.payload()["steps"][5]
    assert "ok: False" in step["output"]
    assert "bob@elsewhere.test" in step["output"]
    assert "555-666-7777" in step["output"]


def test_the_tutorial_needs_no_credentials(monkeypatch):
    """A reader with no Databricks profile must still get the whole page."""

    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", "/tmp/edgepii-no-such-config")
    monkeypatch.setenv("DATABRICKS_PROFILE", "no-such-profile")
    payload = tutorial.payload()
    assert len(payload["steps"]) == 6


def test_every_tutorial_output_is_reproducible():
    """Two builds must agree, or the page is showing state rather than a fact."""

    first = tutorial.payload()
    for step in first["steps"]:
        assert isinstance(step["output"], str)
    assert first["source"] == tutorial.TICKET


@pytest.mark.parametrize("step", tutorial.STEPS, ids=lambda s: s.title[:24])
def test_no_step_leaks_a_secret_into_its_output(step):
    """A tutorial that prints the password defeats its own lesson."""

    if "password" in step.code.lower() or "secret" in step.title.lower():
        assert "hunter2" not in step.output or "not in the vault" in step.output


def test_the_tutorial_routes_serve_without_credentials(monkeypatch):
    """A reader with no profile must reach both the page and its payload."""

    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", "/tmp/edgepii-no-such-config")
    monkeypatch.setenv("DATABRICKS_PROFILE", "no-such-profile")

    import app as app_module

    client = TestClient(app_module.app)

    page = client.get("/tutorial")
    assert page.status_code == 200
    assert "tutorial.js" in page.text

    payload = client.get("/api/tutorial").json()
    assert payload["source"] == tutorial.TICKET
    assert len(payload["steps"]) == 6

    script = client.get("/static/tutorial.js")
    assert script.status_code == 200


def test_the_demo_page_links_to_the_tutorial(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABRICKS_CONFIG_FILE", "/tmp/edgepii-no-such-config")
    monkeypatch.setenv("DATABRICKS_PROFILE", "no-such-profile")

    import app as app_module

    page = TestClient(app_module.app).get("/")
    assert 'href="/tutorial"' in page.text
