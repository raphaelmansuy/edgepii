"""The restore contract. Every case here is a failure a real model produces.

The naive loop in the old docs was:

    for placeholder, real in vault.items():
        answer = answer.replace(placeholder, real)

That loop fails when the model changes the case of a token, invents a token, or
returns PII the vault never held. Each test below pins one of those cases, so a
future edit cannot quietly reintroduce the silence.
"""

from edgepii import Locator, Span, redact, restore


def _masked(prompt, types=None):
    locator = Locator.preset("rules")
    result = locator.locate(prompt, types=types)
    masked, vault = redact(prompt, result.spans)
    return locator, masked, vault


def test_restore_puts_a_value_back():
    _, masked, vault = _masked("Email ada@example.com.")
    assert masked == "Email <EMAIL_1>."

    result = restore("Sent to <EMAIL_1> today.", vault)
    assert result.text == "Sent to ada@example.com today."
    assert result.ok
    assert result.resolved == ("<EMAIL_1>",)
    assert result.unresolved == ()


def test_restore_tolerates_a_lower_case_placeholder():
    """A model lower-cases a token. The old str.replace loop left it in the text."""

    _, _, vault = _masked("Email ada@example.com.")
    result = restore("Sent to <email_1> today.", vault)
    assert result.text == "Sent to ada@example.com today."
    assert result.ok


def test_restore_tolerates_space_drift_inside_the_brackets():
    """A model may drop the underscore, add a space, or pad the brackets."""

    _, _, vault = _masked("Email ada@example.com.")
    for text in (
        "Sent to < EMAIL 1 > today.",
        "Sent to <EMAIL 1> today.",
        "Sent to <EMAIL-1> today.",
        "Sent to <EMAIL_1 > today.",
    ):
        result = restore(text, vault)
        assert result.text == "Sent to ada@example.com today.", text
        assert result.ok, text


def test_restore_does_not_confuse_a_longer_token():
    """<EMAIL_10> must not be eaten by the <EMAIL_1> pattern."""

    vault = {f"<EMAIL_{index}>": f"user{index}@example.com" for index in range(1, 12)}
    result = restore("Send to <EMAIL_10> and <EMAIL_1> and <EMAIL_11>.", vault)
    assert "user10@example.com" in result.text
    assert "user1@example.com" in result.text
    assert "user11@example.com" in result.text
    assert result.ok


def test_restore_reports_a_token_the_vault_never_held():
    """A model can echo a placeholder shape we did not send."""

    _, _, vault = _masked("Email ada@example.com.")
    result = restore("Hello <PERSON_9>, about <EMAIL_1>.", vault)
    assert result.text == "Hello <PERSON_9>, about ada@example.com."
    assert result.unresolved == ("<PERSON_9>",)
    assert not result.ok


def test_restore_reports_pii_the_model_returned():
    """A response can hold PII the masked prompt never contained."""

    locator, _, vault = _masked("Ticket from ada@example.com.")
    answer = "Also grace@example.com called from +852 5555 0101."

    result = restore(answer, vault, locator=locator)
    found = {(span.type, span.text) for span in result.unknown}
    assert ("EMAIL", "grace@example.com") in found
    assert not result.ok


def test_restore_does_not_flag_a_value_it_put_back():
    """Restoration inserts real values by design. Those are not unknown PII."""

    locator, _, vault = _masked("Ticket from ada@example.com.")
    result = restore("I wrote to <EMAIL_1>.", vault, locator=locator)
    assert result.text == "I wrote to ada@example.com."
    assert result.unknown == ()
    assert result.ok


def test_restore_leaves_a_secret_visible_and_reports_it():
    """`redact` never vaults a secret, so restore cannot hide it. Say so."""

    _, _, vault = _masked("password=hunter2 email a@b.co")
    result = restore("Saved <SECRET> for <EMAIL_1>.", vault)
    assert "<SECRET>" in result.text
    assert "<SECRET>" in result.unresolved
    assert not result.ok


def test_restore_keeps_nothing():
    _, _, vault = _masked("Email ada@example.com.")
    before = dict(vault)
    restore("Send to <EMAIL_1>.", vault)
    assert vault == before


def test_restore_on_empty_vault_reports_every_token():
    result = restore("Hello <EMAIL_1>.", {})
    assert result.text == "Hello <EMAIL_1>."
    assert result.unresolved == ("<EMAIL_1>",)
    assert not result.ok


def test_restore_to_dict_shape():
    _, _, vault = _masked("Email ada@example.com.")
    payload = restore("Hi <EMAIL_1>", vault).to_dict()
    assert payload["ok"] is True
    assert payload["text"] == "Hi ada@example.com"
    assert payload["resolved"] == ["<EMAIL_1>"]
    assert payload["unresolved"] == []
    assert payload["unknown"] == []


def test_restore_rejects_a_bad_type():
    for bad in (None, 42, b"bytes"):
        try:
            restore(bad, {})
        except TypeError:
            continue
        raise AssertionError(f"{bad!r} should raise TypeError")


def test_span_to_dict_round_trips():
    span = Span("EMAIL", 0, 5, "a@b.c", None, "rules.email", "email")
    row = span.to_dict()
    assert row["type"] == "EMAIL"
    assert row["text"] == "a@b.c"
    assert row["score"] is None
