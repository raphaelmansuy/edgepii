"""Playwright end-to-end checks. Screenshots land in docs/e2e/screenshots."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "e2e" / "screenshots"

TICKET = (
    "Customer Ada Lovelace called from +852 5555 0101. "
    "Email ada@example.com. Card 4242424242424242. Order 48291."
)
SECRET_NOTE = (
    "Ask Ada Lovelace <ada@example.com> to call +1 202 555 0147 "
    "about ticket 77. Do not include the password hunter2 in the note."
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:  # noqa: BLE001 - server not up yet
            time.sleep(0.2)
    raise RuntimeError(f"server did not start at {url}")


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "demo.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for(base + "/api/health")
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        engine = playwright.chromium.launch()
        yield engine
        engine.close()


@pytest.fixture()
def page(browser, server):
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        device_scale_factor=2,
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    page.goto(server, wait_until="networkidle")
    page.wait_for_selector(".preset")
    yield page
    context.close()


def shot(page, name: str) -> Path:
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / name
    page.screenshot(path=str(path), full_page=True)
    return path


def locate(page, source: str) -> None:
    page.fill("#source", source)
    page.click("#run")
    page.wait_for_selector("#results:not([hidden])", timeout=60_000)


def test_home_renders(page):
    assert page.title() == "edgepii · locate PII spans"
    assert page.locator(".preset").count() >= 5
    assert page.locator("#type-list .type").count() >= 11
    shot(page, "01-home.png")


def test_rules_ticket_spans(page):
    locate(page, TICKET)
    page.wait_for_selector("#span-body tr")
    types = page.locator("#span-body .type-chip").all_inner_texts()
    assert types == ["PHONE", "EMAIL", "PAYMENT"]
    assert page.locator("#span-body .slice-bad").count() == 0
    marks = page.locator(".mark-span").all_inner_texts()
    assert marks == ["+852 5555 0101", "ada@example.com", "4242424242424242"]
    assert "48291" not in marks
    shot(page, "02-rules-ticket.png")


def test_secret_masked_without_vault_leak(page):
    locate(page, SECRET_NOTE)
    page.wait_for_selector("#span-body tr")
    masked = page.locator("#masked").inner_text()
    assert "<SECRET>" in masked
    assert "hunter2" not in masked
    assert "ticket 77" in masked
    vault = page.locator("#vault-body").inner_text()
    assert "hunter2" not in vault
    assert "<EMAIL_1>" in vault
    shot(page, "03-secret-note.png")


def test_type_filter_hides_person(page):
    page.click("#types-none")
    page.click('[data-type="EMAIL"]')
    locate(page, "Write to ada@example.com or to Ada Lovelace in Lisbon.")
    page.wait_for_selector("#span-body tr")
    types = page.locator("#span-body .type-chip").all_inner_texts()
    assert types == ["EMAIL"]
    assert page.locator(".mark-span").all_inner_texts() == ["ada@example.com"]
    shot(page, "04-email-only.png")


def test_chinese_line(page):
    page.click('[data-sample="chinese"]')
    page.click("#run")
    page.wait_for_selector("#results:not([hidden])")
    types = page.locator("#span-body .type-chip").all_inner_texts()
    assert "PHONE" in types and "EMAIL" in types
    assert page.locator("#span-body .slice-bad").count() == 0
    shot(page, "05-chinese.png")


def test_numbered_placeholders(page):
    page.click('[data-sample="numbered"]')
    page.click("#run")
    page.wait_for_selector("#results:not([hidden])")
    masked = page.locator("#masked").inner_text()
    assert masked.count("<EMAIL_1>") == 2
    assert "<EMAIL_2>" in masked
    vault = page.locator("#vault-body").inner_text()
    assert "ada@example.com" in vault
    assert "grace@example.com" in vault
    shot(page, "06-placeholders.png")


def test_long_text_offsets(page):
    page.click('[data-sample="long"]')
    page.click("#run")
    page.wait_for_selector("#results:not([hidden])")
    rows = page.locator("#span-body tr").count()
    assert rows == 1
    assert page.locator("#span-body .slice-bad").count() == 0
    shot(page, "07-long-text.png")


def test_empty_source_is_refused(page):
    page.click("#clear")
    page.click("#run")
    page.wait_for_function(
        "() => document.getElementById('status').textContent.includes('Add some text')"
    )
    assert page.locator("#results").is_hidden()
    assert "Add some text" in page.locator("#status").inner_text()
    shot(page, "08-empty-state.png")


def test_narrow_viewport(page):
    page.set_viewport_size({"width": 430, "height": 900})
    locate(page, TICKET)
    page.wait_for_selector("#span-body tr")
    shot(page, "09-narrow.png")


def test_payload_matches_page(page):
    page.fill("#source", TICKET)
    page.click("#run")
    page.wait_for_selector("#results:not([hidden])")
    body = page.evaluate(
        """async () => {
            const response = await fetch('/api/locate', {
                method: 'POST',
                headers: {'content-type': 'application/json'},
                body: JSON.stringify({source: document.getElementById('source').value,
                                      preset: 'rules', types: []}),
            });
            return response.json();
        }"""
    )
    assert body["slice_ok"] is True
    assert json.dumps(body)[:1] == "{"


def test_copy_json_button(page):
    locate(page, TICKET)
    page.wait_for_selector("#span-body tr")
    page.click("#copy-json")
    page.wait_for_function(
        "() => document.getElementById('copy-json').textContent === 'Copied'"
    )
    copied = page.evaluate("() => navigator.clipboard.readText()")
    assert '"type": "PHONE"' in copied
    shot(page, "11-copy-json.png")


def test_score_floor_is_caller_policy(page):
    locate(page, TICKET)
    page.wait_for_selector("#span-body tr")
    # The rules lane reports null for email and phone, and 1.0 for the card.
    assert page.locator("#span-body .score-none").count() == 2
    page.fill("#min-score", "0.9")
    page.dispatch_event("#min-score", "input")
    assert page.locator("#min-score-value").inner_text() == "0.90"
    page.click("#run")
    # A floor cannot compare a span that has no score, so those spans stay. A
    # redaction tool that dropped them would send the email out in the clear.
    page.wait_for_function(
        "() => document.querySelectorAll('#span-body tr').length === 3"
    )
    assert page.locator("#span-body .score-none").count() == 2

    # The stricter behaviour is one click away, and it says what it costs.
    page.check("#drop-unscored")
    page.wait_for_function(
        "() => document.querySelectorAll('#span-body tr').length === 1"
    )
    assert page.locator("#span-body .type-chip").all_inner_texts() == ["PAYMENT"]
    assert page.locator("#span-body .score-none").count() == 0
    shot(page, "12-score-floor.png")


def test_model_lane_finds_a_name(page):
    ready = page.evaluate(
        """async () => {
            const response = await fetch('/api/presets');
            const body = await response.json();
            const row = body.presets.find((item) => item.name === 'en-closed');
            return Boolean(row && row.ready);
        }"""
    )
    if not ready:
        pytest.skip("the hf extra is not installed in this environment")

    page.click('[data-preset="en-closed"]')
    page.click("#types-none")
    page.click('[data-type="PERSON"]')
    locate(page, "Ask Ada Lovelace to call the help desk.")
    page.wait_for_selector("#span-body tr", timeout=180_000)
    types = page.locator("#span-body .type-chip").all_inner_texts()
    assert types and set(types) == {"PERSON"}
    marks = " ".join(page.locator(".mark-span").all_inner_texts())
    assert "Ada" in marks and "Lovelace" in marks
    assert page.locator("#span-body .slice-bad").count() == 0
    shot(page, "10-model-lane.png")


def test_reidentification_risk_is_shown(page):
    """A complete mask can still leave a person identifiable. Say so in the UI."""

    locate(page, "Patient born 1985-03-14, ZIP 94110, male, follow-up booked.")

    # The rules lane finds no span here, which is the point.
    page.wait_for_selector("#quasi-block:not([hidden])")
    items = page.locator("#quasi-list .quasi-item")
    assert items.count() == 1
    assert "zip_dob_sex" in items.first.inner_text()
    assert "high risk" in items.first.inner_text()

    # And it disappears when the fields are not a combination.
    locate(page, "Patient followed up on 2026-11-04 about order 94110.")
    page.wait_for_selector("#quasi-block", state="hidden")
