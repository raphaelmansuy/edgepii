"""Each test names the source of a rule. No invented constant is allowed here."""

from __future__ import annotations

import ipaddress
import re

import pytest

from edgepii import Locator, Span, redact
from edgepii.detectors import rules
from edgepii.labelmap import load_taxonomy
from edgepii.merge import merge_spans
from edgepii.windows import split_windows


def _texts(source: str, labels: list[str]) -> list[str]:
    return [
        source[hit.start : hit.end]
        for hit in rules.RuleDetector().locate(source, labels)
    ]


def test_luhn_follows_iso_7812_length_and_leading_digit():
    assert rules._luhn_ok("4242424242424242")
    assert rules._luhn_ok("4242424242424243") is False
    assert rules._luhn_ok("4111111111111111")
    # 8 digits is the ISO/IEC 7812-1 minimum for a PAN.
    assert rules._luhn_ok("12345674")
    assert rules._luhn_ok("1234567") is False
    # A PAN starts with a major industry identifier in 1 to 9.
    assert rules._luhn_ok("0000000000000000") is False


def test_iban_uses_mod_97():
    assert rules._iban_ok("GB82WEST12345698765432")
    assert rules._iban_ok("GB00WEST12345698765432") is False


def test_ip_rules_use_the_stdlib_validator():
    assert rules._ip_ok("203.0.113.10")
    assert rules._ip_ok("2001:db8::1")
    assert rules._ip_ok("12:34:56") is False
    assert rules._ip_ok("2026:11:04") is False
    assert rules._ip_ok("256.1.1.1") is False


def test_every_ip_span_passes_the_stdlib_validator():
    source = "Host 203.0.113.10, v6 2001:db8::8a2e:370:7334, time 12:34:56, date 2026:11:04."
    found = _texts(source, ["ip"])
    assert found == ["203.0.113.10", "2001:db8::8a2e:370:7334"]
    for value in found:
        ipaddress.ip_address(value)


def test_a_short_local_number_is_not_a_phone():
    # IS_POSSIBLE_LOCAL_ONLY is a subscriber fragment, not a dialable number.
    source = "Customer 48291 called from +852 5555 0101."
    assert _texts(source, ["phone"]) == ["+852 5555 0101"]


def test_a_valid_number_scores_one_and_a_shape_scores_null():
    valid = "Call +1 202 555 0147 now."
    shape = "Call +852 5555 0101 now."
    valid_hit = rules.RuleDetector().locate(valid, ["phone"])[0]
    shape_hit = rules.RuleDetector().locate(shape, ["phone"])[0]
    assert valid_hit.score == 1.0
    assert shape_hit.score is None


def test_card_digits_inside_an_iban_are_not_a_card():
    source = "Wire GB82WEST12345698765432 today."
    assert _texts(source, ["card_number"]) == []
    assert _texts(source, ["iban"]) == ["GB82WEST12345698765432"]


def test_email_respects_rfc_5321_local_part_limit():
    at_limit = ("a" * 64) + "@example.com"
    over_limit = ("a" * 65) + "@example.com"
    assert _texts(at_limit, ["email"]) == [at_limit]
    assert _texts(over_limit, ["email"]) == []


def test_secret_assignment_and_mention():
    assert _texts("api_key = sk-live-9f8a7b now", ["password"]) == ["sk-live-9f8a7b"]
    assert _texts("the password hunter2 is set", ["password"]) == ["hunter2"]
    # A bare word after a cue is prose, not a value.
    assert _texts("the password is set", ["password"]) == []
    assert _texts("the password reset failed", ["password"]) == []


def test_no_score_floor_ships_with_the_library():
    taxonomy = load_taxonomy()
    span = Span("PERSON", 0, 4, "xxxx", 0.01, "model.low", "person")
    assert len(merge_spans([span], taxonomy, {"PERSON"})) == 1
    assert merge_spans([span], taxonomy, {"PERSON"}, min_score=0.5) == []


def test_a_span_with_no_score_cannot_meet_a_floor():
    taxonomy = load_taxonomy()
    shaped = Span("EMAIL", 0, 5, "aaaaa", None, "rules.email", "email")
    assert len(merge_spans([shaped], taxonomy, {"EMAIL"})) == 1
    assert merge_spans([shaped], taxonomy, {"EMAIL"}, min_score=0.1) == []


def test_threshold_field_is_gone_from_the_taxonomy():
    info = load_taxonomy().types["EMAIL"]
    assert not hasattr(info, "threshold")


def test_every_documented_example_keeps_the_slice_invariant():
    from demo.samples import SAMPLES

    locator = Locator.preset("rules")
    for sample in SAMPLES:
        result = locator.locate(sample["source"])
        for span in result.spans:
            assert sample["source"][span.start : span.end] == span.text


def test_windows_always_advance_and_never_exceed_max():
    source = "word " * 500
    for max_chars in (16, 33, 64, 129):
        windows = split_windows(source, max_chars, overlap_chars=8)
        assert windows[0][0] == 0
        assert windows[-1][1] == len(source)
        previous_start = -1
        for start, end in windows:
            assert start > previous_start
            assert end - start <= max_chars
            previous_start = start


def test_windows_cut_on_a_space_when_one_exists():
    source = ("alpha " * 40).strip()
    windows = split_windows(source, 40, overlap_chars=0)
    for start, end in windows[:-1]:
        assert source[start:end].endswith(" ") or " " not in source[start:end]


def test_merge_is_deterministic_across_input_order():
    taxonomy = load_taxonomy()
    a = Span("EMAIL", 0, 5, "aaaaa", 0.9, "rules.email", "email")
    b = Span("PERSON", 0, 5, "aaaaa", 0.9, "model.p", "person")
    forward = merge_spans([a, b], taxonomy, {"EMAIL", "PERSON"})
    backward = merge_spans([b, a], taxonomy, {"EMAIL", "PERSON"})
    assert forward == backward


def test_payload_has_no_duplicate_span():
    source = "ada@example.com and +852 5555 0101"
    result = Locator.preset("rules").locate(source)
    keys = [(span.type, span.start, span.end) for span in result.spans]
    assert len(keys) == len(set(keys))
    masked, vault = redact(source, result.spans)
    assert masked == "<EMAIL_1> and <PHONE_1>"
    assert len(vault) == 2


def test_no_rule_contains_a_magic_probability():
    text = open(rules.__file__, encoding="utf-8").read()
    assert "0.8" not in text
    assert "0.80" not in text
    assert re.search(r"Hit\([^)]*0\.[0-9]+", text) is None
