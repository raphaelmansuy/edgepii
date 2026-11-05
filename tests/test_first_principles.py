"""Outcome tests derived from the source/masking contract, independent of weights."""

import importlib.util
import itertools
from pathlib import Path
from types import SimpleNamespace

import pytest

from edgepii import Locator, Span, redact, restore
from edgepii.detectors.hf_token import HfTokenDetector
from edgepii.eval.corpora import materialize_spy
from edgepii.eval.coverage import character_counts, covered, union_ranges
from edgepii.labelmap import load_taxonomy
from edgepii.merge import merge_spans
from edgepii.windows import checked_windows


def test_losing_bridge_cannot_hide_disjoint_identifiers():
    source = "x" * 30
    spans = [Span("PERSON", 0, 20, source[:20], .9, "model.person", "person"),
             Span("GOV_ID", 5, 9, source[5:9], .9, "model.id", "national_id"),
             Span("EMAIL", 18, 30, source[18:], None, "rules.email", "email")]
    for order in itertools.permutations(spans):
        result = merge_spans(list(order), load_taxonomy(), {"PERSON", "GOV_ID", "EMAIL"})
        assert [(s.type, s.start, s.end) for s in result] == [("GOV_ID", 5, 9), ("EMAIL", 18, 30)]
        assert all(source[s.start:s.end] == s.text for s in result)


def test_dense_bridge_does_not_remove_separate_high_priority_spans():
    source = "x" * 20000
    cards = [Span("PAYMENT", i, i+4, source[i:i+4], 1., "rules.card", "card_number")
             for i in range(0, 20000, 10)]
    bridge = Span("PERSON", 0, len(source), source, .99, "model", "person")
    assert merge_spans([bridge, *reversed(cards)], load_taxonomy(), {"PERSON", "PAYMENT"}) == cards


def test_secret_overlap_never_restores_a_credential():
    source = "secretvalue and ada@example.com"
    spans = [Span("PERSON", 0, 20, source[:20], .9, "model", "person"),
             Span("SECRET", 0, 11, source[:11], None, "rules.secret", "password"),
             Span("EMAIL", 16, 31, source[16:31], None, "rules.email", "email")]
    kept = merge_spans(spans, load_taxonomy(), {"PERSON", "SECRET", "EMAIL"})
    masked, vault = redact(source, kept)
    assert "secretvalue" not in str(vault)
    assert "secretvalue" not in masked
    assert "ada@example.com" in restore(masked, vault).text


def test_checked_windows_cover_dense_unicode_without_token_overflow():
    source = "中" * 113 + "ada@example.com" + "🧑‍💻" * 17
    count = lambda text: 3 + sum(4 if ord(char) > 127 else 1 for char in text)
    windows = list(checked_windows(source, count, 64))
    assert windows[0][0] == 0 and windows[-1][1] == len(source)
    for i, (start, end) in enumerate(windows):
        assert start < end and count(source[start:end]) <= 64
        if i:
            assert windows[i-1][0] < start <= windows[i-1][1]
    assert any("ada@example.com" in source[a:b] for a,b in windows)


def test_impossible_schema_or_character_fails_without_copying_source():
    with pytest.raises(ValueError, match="schema"):
        list(checked_windows("private-source", lambda text: 100, 64))
    with pytest.raises(ValueError) as exc:
        list(checked_windows("敏", lambda text: len(text) * 100, 64))
    assert "敏" not in str(exc.value)


def test_hf_tail_is_inferred_with_original_offsets():
    source = "中" * 113 + "ada@example.com"
    calls = []
    class Pipe:
        def tokenizer(self, text, **kwargs):
            return {"input_ids": [0] * (2 + sum(4 if ord(c) > 127 else 1 for c in text))}
        def __call__(self, text):
            assert len(self.tokenizer(text)["input_ids"]) <= 64
            calls.append(text)
            index = text.find("ada@example.com")
            return [] if index < 0 else [{"start":index,"end":index+15,"entity_group":"email","score":.9}]
    detector = HfTokenDetector.__new__(HfTokenDetector)
    detector.repo_id = "fake"
    detector._pipe = Pipe()
    detector.token_budget = 64
    result = Locator.from_detectors([detector]).locate(source, types=["EMAIL"], fold=False)
    assert [(s.start,s.end,s.text) for s in result.spans] == [(113,128,"ada@example.com")]
    assert len(calls) > 1


def test_character_metrics_count_union_and_complete_containment():
    gold = [("PERSON",0,4),("EMAIL",2,6)]
    predictions = [("wrong",0,3),("wrong",3,8)]
    assert character_counts(gold,predictions) == (6,8,6)
    masks = union_ranges((r[1],r[2]) for r in predictions)
    assert covered(0,6,masks)
    assert not covered(0,9,masks)


def test_report_exposes_coverage_lost_to_overlap_policy_without_source_values():
    from edgepii.eval.corpora import Doc
    from edgepii.eval.runner import score_docs
    from edgepii.protocol import Hit
    source = "x" * 30
    class Detector:
        def locate(self, text, labels):
            return [Hit("person", 0, 20, .9, "model"),
                    Hit("government_id", 5, 9, .9, "model"),
                    Hit("email", 18, 30, .9, "model")]
    locator = Locator.from_detectors([Detector()])
    doc = Doc("test", source, (), (("PERSON", 0, 20), ("EMAIL", 18, 30)))
    result = score_docs(locator, [doc], "test", {"PERSON", "GOV_ID", "EMAIL"}).to_dict()
    assert result["pre_policy_candidates"]["fully_contained_gold_spans"] == 2
    assert result["containment"]["fully_contained_gold_spans"] == 1
    assert "_candidate_ranges" not in locator.locate(source).to_dict()


def test_repeated_value_needs_every_mention_and_audited_negatives_measure_damage():
    from edgepii.eval.corpora import Doc
    from edgepii.eval.runner import score_docs
    from edgepii.protocol import Hit
    class Detector:
        def locate(self, text, labels):
            # A wrong type still masks the first email; the second is missed.
            return [Hit("person", 0, 15, .9, "model")] if "@" in text else [Hit("person", 0, 5, .9, "model")]
    docs = [Doc("repeat", "ada@example.com then ada@example.com", (),
                (("EMAIL", 0, 15), ("EMAIL", 21, 36))),
            Doc("audited-negative", "Order 48291 ships Tuesday.", (), ())]
    result = score_docs(Locator.from_detectors([Detector()]), docs, "test", {"PERSON", "EMAIL"}).to_dict()
    coverage = result["containment"]
    assert result["tp"] == 0
    assert coverage["character_recall"] == .5
    assert coverage["masking_precision"] == .75
    assert coverage["repeated_identifiers"] == 1
    assert coverage["fully_contained_repeated_identifiers"] == 0
    assert coverage["zero_gold_document_mask_rate"] == 1
    assert coverage["zero_gold_masked_characters"] == 5
    assert coverage["zero_gold_masked_character_fraction"] == 5 / len(docs[1].text)
    assert coverage["masked_character_fraction"] == 20 / sum(len(doc.text) for doc in docs)


def test_unknown_model_labels_are_counted_without_serializing_them():
    from edgepii.protocol import Hit
    class Detector:
        def locate(self, source, labels):
            return [Hit("unmapped-ada@example.com", 0, 3, .9, "model")]
    result = Locator.from_detectors([Detector()]).locate("Ada")
    assert result.unmapped == 1 and result.dropped == 0 and not result.spans
    assert "ada@example.com" not in str(result.to_dict())


def test_spy_v2_ids_are_government_shapes_and_legacy_is_explicit():
    import re
    records=[{"tokens":["<ID>"],"ent_tags":["B-ID_NUM"],"trailing_whitespaces":[False]}]
    current=materialize_spy(records,42)
    legacy=materialize_spy(records,42,protocol="legacy-v1")
    assert re.fullmatch(r"\d{3}-\d{2}-\d{4}","".join(current[0]["tokens"]))
    assert "RIPE" in "".join(legacy[0]["tokens"])
    assert current == materialize_spy(records,42)
    assert current != legacy


def test_spy_does_not_mutate_global_faker_randomness():
    from faker import Faker
    Faker.seed(123)
    expected=Faker().name()
    Faker.seed(123)
    materialize_spy([],42)
    assert Faker().name() == expected


def test_native_opf_rejects_decode_mismatch_and_invalid_claims():
    spec=importlib.util.spec_from_file_location("edgepii_native_opf_test", Path(__file__).parents[1]/"modal/native_opf.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result=SimpleNamespace(warning=None,text="Ada",summary={},detected_spans=[SimpleNamespace(label="private_person",start=0,end=3,text="Ada")])
    detector=module.NativeOpf(runner=SimpleNamespace(redact=lambda text:result))
    assert detector.locate("Ada")[0].claimed_text == "Ada"
    result.text="Bob"
    with pytest.raises(ValueError,match="original source"):
        detector.locate("Ada")
    result.text="Ada"
    result.detected_spans[0].text="Bob"
    with pytest.raises(ValueError,match="invalid original-source"):
        detector.locate("Ada")
