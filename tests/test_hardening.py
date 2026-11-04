"""Obfuscation, the score floor, and the tool-call plane.

Each test here reproduces a defect found in the 0.2.0 audit (docs/14). A test
that fails means the library went back to leaking a value it claimed to mask.
"""

import json

import pytest

from edgepii import Locator, mask_mapping, redact, restore, restore_mapping
from edgepii.normalize import fold, needs_fold


def _loc():
    return Locator.preset("rules")


# --------------------------------------------------------------------------
# D1. A look-alike character must not produce a partial span.
# --------------------------------------------------------------------------


def test_cyrillic_a_does_not_leave_a_stray_character():
    """The worst 0.2.0 defect: a mask that looked complete and was not."""

    source = "Email \u0430da@example.com"  # Cyrillic a, then da@example.com
    spans = _loc().locate(source).spans

    assert len(spans) == 1
    # The span must cover the confusable character as well as the rest.
    assert spans[0].start == 6
    assert source[spans[0].start : spans[0].end] == "\u0430da@example.com"

    masked, vault = redact(source, spans)
    assert masked == "Email <EMAIL_1>"
    assert vault == {"<EMAIL_1>": "\u0430da@example.com"}


def test_a_span_still_slices_the_source_string():
    """Folding must never move the public offsets off the caller's string."""

    for source in (
        "Email \u0430da@example.com",
        "Email ada\uff20example.com",
        "Email ada@\u200bexample.com",
        "Card \uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12",
    ):
        for span in _loc().locate(source).spans:
            assert source[span.start : span.end] == span.text, source


def test_fullwidth_at_sign_is_found():
    source = "Email ada\uff20example.com"
    spans = _loc().locate(source).spans
    assert [span.type for span in spans] == ["EMAIL"]
    assert spans[0].text == "ada\uff20example.com"


def test_zero_width_space_inside_an_address_is_found():
    source = "Email ada@\u200bexample.com"
    spans = _loc().locate(source).spans
    assert [span.type for span in spans] == ["EMAIL"]
    # The span covers the invisible character too, so a mask removes it.
    assert "\u200b" in spans[0].text


def test_fullwidth_digits_are_found():
    source = "Card \uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12\uff14\uff12"
    spans = _loc().locate(source).spans
    assert [span.type for span in spans] == ["PAYMENT"]


def test_several_confusables_in_one_value():
    source = "Email \u0430d\u0430@ex\u0430mple.com"
    spans = _loc().locate(source).spans
    assert len(spans) == 1
    assert source[spans[0].start : spans[0].end] == "\u0430d\u0430@ex\u0430mple.com"


def test_folding_can_be_turned_off():
    source = "Email ada\uff20example.com"
    assert _loc().locate(source, fold=False).spans == ()
    assert len(_loc().locate(source).spans) == 1


def test_plain_text_is_not_touched_by_folding():
    """A clean string must produce exactly the same spans as before."""

    source = "Email ada@example.com and card 4242424242424242."
    spans = _loc().locate(source).spans
    assert [(s.type, s.text) for s in spans] == [
        ("EMAIL", "ada@example.com"),
        ("PAYMENT", "4242424242424242"),
    ]


def test_fold_only_reports_change_when_it_changes_something():
    assert not needs_fold("plain ascii text")
    assert needs_fold("ada\uff20example.com")


def test_fold_maps_back_to_the_source_index():
    source = "abc\u0430def"
    folded = fold(source)
    assert folded.text == "abcadef"
    # Index 3 in the folded text is the Cyrillic character at source index 3.
    assert folded.to_source(3, 4) == (3, 4)
    assert folded.to_source(0, 7) == (0, 7)


# --------------------------------------------------------------------------
# D2. A score floor must not remove a value that has no score.
# --------------------------------------------------------------------------


def test_a_floor_keeps_the_types_that_have_no_score():
    source = "Email ada@example.com, phone +852 5555 0101, card 4242424242424242."
    kept = {span.type for span in _loc().locate(source, min_score=0.5).spans}
    assert kept == {"EMAIL", "PHONE", "PAYMENT"}

    masked, _ = redact(source, _loc().locate(source, min_score=0.5).spans)
    assert "ada@example.com" not in masked
    assert "5555" not in masked


def test_the_stricter_behaviour_is_opt_in():
    source = "Email ada@example.com, card 4242424242424242."
    kept = {
        span.type
        for span in _loc().locate(source, min_score=0.5, drop_unscored=True).spans
    }
    assert kept == {"PAYMENT"}


def test_a_low_score_is_still_filtered():
    """The floor keeps working for spans that do carry a score."""

    from edgepii.merge import merge_spans
    from edgepii.labelmap import load_taxonomy
    from edgepii.span import Span

    taxonomy = load_taxonomy("2026.11")
    low = Span("PERSON", 0, 4, "xxxx", 0.2, "model.low", "person")
    assert merge_spans([low], taxonomy, {"PERSON"}, min_score=0.5) == []
    assert len(merge_spans([low], taxonomy, {"PERSON"}, min_score=0.1)) == 1


# --------------------------------------------------------------------------
# D3 and the tool-call plane.
# --------------------------------------------------------------------------


def test_mask_mapping_masks_each_field_and_keeps_a_path():
    args = {"customer": {"email": "ada@example.com"}, "note": "card 4242424242424242"}
    masked = mask_mapping(args, _loc())

    assert masked.value["customer"]["email"] == "<EMAIL_1_0>"
    assert "4242424242424242" not in masked.value["note"]
    paths = {hit.path for hit in masked.hits}
    assert paths == {"customer.email", "note"}
    # The journal must not carry a value.
    assert "ada@example.com" not in json.dumps(masked.to_dict())


def test_two_fields_with_the_same_type_do_not_collide():
    """0.2.0 lost the second value: both leaves became <EMAIL_1>."""

    args = {
        "customer": {"email": "ada@example.com"},
        "billing": {"email": "grace@example.com"},
    }
    masked = mask_mapping(args, _loc())
    assert len(masked.vault) == 2
    assert set(masked.vault.values()) == {"ada@example.com", "grace@example.com"}

    restored = restore_mapping(masked.value, masked.vault)
    assert restored.value == args
    assert restored.ok


def test_mask_mapping_does_not_mutate_the_input():
    args = {"email": "ada@example.com"}
    mask_mapping(args, _loc())
    assert args == {"email": "ada@example.com"}


def test_mask_mapping_walks_lists_and_keeps_the_shape():
    args = {"recipients": ["ada@example.com", {"cc": "grace@example.com"}]}
    masked = mask_mapping(args, _loc())
    assert isinstance(masked.value["recipients"], list)
    assert isinstance(masked.value["recipients"][1], dict)
    assert "ada@example.com" not in json.dumps(masked.value)
    assert "grace@example.com" not in json.dumps(masked.value)


def test_mask_mapping_leaves_numbers_and_bools_alone():
    args = {"count": 3, "ok": True, "none": None, "email": "ada@example.com"}
    masked = mask_mapping(args, _loc())
    assert masked.value["count"] == 3
    assert masked.value["ok"] is True
    assert masked.value["none"] is None


def test_a_decoded_json_payload_hides_no_escaped_address():
    """D3: an escaped address is only visible after the JSON decoder runs."""

    raw = '{"query": "look up ada\\u0040example.com"}'
    assert _loc().locate(json.loads(raw)["query"]).spans or False  # decoded, so found
    parsed = json.loads(raw)
    masked = mask_mapping(parsed, _loc())
    assert "ada@example.com" not in json.dumps(masked.value)


def test_restore_mapping_reports_a_placeholder_it_cannot_resolve():
    args = {"email": "<EMAIL_1_0>", "other": "<PERSON_9>"}
    restored = restore_mapping(args, {"<EMAIL_1_0>": "ada@example.com"})
    assert restored.value["email"] == "ada@example.com"
    assert restored.unresolved == ("<PERSON_9>",)
    assert not restored.ok


def test_restore_mapping_can_check_the_response_for_new_pii():
    locator = _loc()
    masked = mask_mapping({"email": "ada@example.com"}, locator)
    inbound = {"email": masked.value["email"], "note": "also grace@example.com"}
    restored = restore_mapping(inbound, masked.vault, locator=locator)
    assert restored.value["email"] == "ada@example.com"
    assert [(s.type, s.text) for s in restored.unknown] == [("EMAIL", "grace@example.com")]
    assert not restored.ok


def test_masking_and_restoring_an_empty_tree_is_a_no_op():
    assert mask_mapping({}, _loc()).value == {}
    assert mask_mapping({}, _loc()).vault == {}
    assert restore_mapping({}, {}).value == {}


def test_a_masked_tree_round_trips_through_json():
    args = {"a": "ada@example.com", "b": ["grace@example.com"]}
    masked = mask_mapping(args, _loc())
    wire = json.dumps(masked.value)
    restored = restore_mapping(json.loads(wire), masked.vault)
    assert restored.value == args
