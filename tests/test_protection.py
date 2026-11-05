"""First-principles oracles for opt-in protection, independent of model quality."""

import itertools
import json
import random

import pytest

from edgepii import (IncompleteDetectionError, Locator, Span, protection_plan,
                     redact, redact_protected, protect_mapping, restore, restore_mapping)
from edgepii.protocol import Hit


def span(source, kind, start, end, score=None):
    return Span(kind, start, end, source[start:end], score, "test.detector", kind.lower())


def test_partial_secret_overlap_protects_whole_identifier_without_vault_fragments():
    source = "ABCDEFGHIJKLMNO"
    candidates = [span(source, "GOV_ID", 0, 15), span(source, "SECRET", 5, 10)]
    for order in itertools.permutations(candidates):
        plan = protection_plan(source, order)
        assert [(s.start,s.end,s.irreversible) for s in plan.segments] == [(0,15,True)]
        masked, vault = redact_protected(source, plan)
        assert masked == "<SECRET>" and vault == {}
        assert restore(masked, vault).text == "<SECRET>"


def test_independent_typed_selection_and_union_protection():
    source = "x" * 30
    class Detector:
        def locate(self, text, labels):
            return [Hit("person",0,20,.9,"model"),Hit("government_id",5,9,.9,"model"),
                    Hit("email",18,30,.9,"model")]
    locator = Locator.from_detectors([Detector()])
    assert [(s.start,s.end) for s in locator.locate(source).spans] == [(5,9),(18,30)]
    plan = locator.plan(source)
    assert [(s.start,s.end) for s in plan.segments] == [(0,30)]
    masked, vault = redact_protected(source, plan)
    assert "PERSON" not in masked and masked == "<PROTECTED_1>"
    assert restore(masked, vault).text == source


def test_seeded_interval_oracle_coverage_and_secret_exclusion():
    rng = random.Random(518)
    source = "".join(chr(0x1000+i) for i in range(120))
    for _ in range(100):
        candidates = []
        expected, secret_chars = set(), set()
        for _ in range(rng.randrange(1,18)):
            a = rng.randrange(len(source)); b = rng.randrange(a+1,len(source)+1)
            kind = rng.choice(["PERSON","EMAIL","GOV_ID","SECRET"])
            candidates.append(span(source,kind,a,b))
            expected.update(range(a,b))
            if kind == "SECRET": secret_chars.update(source[a:b])
        plan = protection_plan(source,candidates)
        actual = {i for s in plan.segments for i in range(s.start,s.end)}
        assert actual == expected
        assert plan == protection_plan(source,list(reversed(candidates)))
        masked,vault = redact_protected(source,plan)
        assert not set("".join(vault.values())) & secret_chars
        if not secret_chars: assert restore(masked,vault).text == source


def test_known_secret_repetitions_are_irreversible_even_under_other_labels():
    source = "hunter2 then hunter2"
    candidates = [span(source,"SECRET",0,7),span(source,"PERSON",13,20)]
    masked,vault = redact_protected(source,protection_plan(source,candidates))
    assert masked == "<SECRET> then <SECRET>" and vault == {}


def test_overlap_repetitions_include_all_literal_occurrences():
    source = "ababa"
    plan = protection_plan(source,[span(source,"SECRET",0,3)])
    assert [(s.start,s.end) for s in plan.segments] == [(0,5)]
    assert redact_protected(source,plan) == ("<SECRET>",{})


def test_plan_is_bound_to_source_without_serializing_source_or_hash():
    source = "Ada 🧑‍💻 e\u0301 mail"
    plan = protection_plan(source,[span(source,"PERSON",0,3)])
    assert "Ada" not in json.dumps(plan.to_dict())
    assert plan._source_fingerprint not in json.dumps(plan.to_dict())
    assert restore(*redact_protected(source,plan)).text == source
    with pytest.raises(ValueError,match="does not match"):
        redact_protected("Bob"+source[3:],plan)


def test_placeholder_literals_do_not_alias_generated_tokens():
    source = "Keep < protected-1 > then Ada"
    plan = protection_plan(source,[span(source,"PERSON",25,28)])
    masked,vault = redact_protected(source,plan)
    assert "<PROTECTED_1>" not in vault
    assert restore(masked,vault).text == source


@pytest.mark.parametrize("candidate", [Span("PERSON",0,3,"Bob",None,"m","person"),
    Span("PERSON",-1,3,"Ada",None,"m","person"),Span("PERSON",0,5,"Ada",None,"m","person")])
def test_bad_candidates_raise_without_source_or_offset_repair(candidate):
    with pytest.raises(ValueError) as exc: protection_plan("Ada",[candidate])
    assert "Ada" not in str(exc.value) and "Bob" not in str(exc.value)


def test_explicit_threshold_and_unscored_policy_apply_before_coverage():
    source = "A B C"
    candidates = [span(source,"PERSON",0,1,.1),span(source,"EMAIL",2,3,None),span(source,"PERSON",4,5,.9)]
    assert [(s.start,s.end) for s in protection_plan(source,candidates,min_score=.5).segments] == [(2,3),(4,5)]
    assert [(s.start,s.end) for s in protection_plan(source,candidates,min_score=.5,drop_unscored=True).segments] == [(4,5)]


def test_strict_diagnostics_reject_incomplete_detection():
    class Detector:
        def locate(self, text, labels):return [Hit("person",0,99,.9,"model")]
    locator=Locator.from_detectors([Detector()])
    with pytest.raises(IncompleteDetectionError):locator.plan("Ada")
    assert locator.plan("Ada",strict=False).dropped == 1
    with pytest.raises(IncompleteDetectionError):protection_plan("Ada",[],unmapped=1)


def test_mapping_secret_reuse_across_leaves_is_never_vaulted():
    source={"password":"password hunter2","copy":"hunter2","contact":"ada@example.com","n":7}
    result=protect_mapping(source,Locator.preset("rules"))
    assert source["copy"] == "hunter2"
    assert "hunter2" not in str(result.value) and "hunter2" not in str(result.vault)
    assert result.value["copy"] == "<SECRET>" and result.value["n"] == 7
    assert restore_mapping(result.value,result.vault).value["contact"] == source["contact"]
    assert result.changed


def test_mapping_round_trip_and_literal_placeholder_collision():
    source={"a":"a@example.com","b":["b@example.com","< protected-1-0 >"],"c":(True,7)}
    result=protect_mapping(source,Locator.preset("rules"))
    assert len(result.vault) == 2
    assert restore_mapping(result.value,result.vault).value == source


def test_mapping_diagnostics_survive_when_all_predictions_are_rejected():
    from edgepii import mask_mapping
    class Detector:
        def locate(self,text,labels):return [Hit("person",0,99,.5,"m")]
    result=mask_mapping({"v":"Ada"},Locator.from_detectors([Detector()]))
    assert result.dropped == 1


def test_secret_only_mapping_changed_is_true():
    from edgepii import mask_mapping
    result=mask_mapping({"v":"password hunter2"},Locator.preset("rules"))
    assert result.changed and result.vault == {}


def test_actual_mask_and_report_preserve_high_severity_candidate_coverage():
    from edgepii.eval.corpora import Doc
    from edgepii.eval.runner import score_docs
    source="ABCDEFGHIJKLMNO"
    class Detector:
        def locate(self,text,labels):
            return [Hit("government_id",0,15,.9,"model"),Hit("secret",5,10,None,"rules.secret")]
    locator=Locator.from_detectors([Detector()])
    row=score_docs(locator,[Doc("test",source,(),(("GOV_ID",0,15),))],"test",{"GOV_ID","SECRET"}).to_dict()
    assert row["high_severity_leaks"] == 1
    assert row["protection_plan"]["high_severity_leaks"] == 0
    assert row["protection_plan"]["span_recall"] == 1
    assert row["protection_plan"]["irreversible_characters"] == 15
    masked,vault=redact_protected(source,locator.plan(source))
    assert masked == "<SECRET>" and vault == {}


def test_explicit_field_policy_masks_unrecognizable_values_without_model_calls():
    class Detector:
        def locate(self,*args):raise AssertionError("field policy should bypass detector")
    locator=Locator.from_detectors([Detector()])
    result=protect_mapping({"password":"hunter2","ssn":"not-even-a-valid-id"},locator,
                           field_types={("password",):"SECRET",("ssn",):"GOV_ID"})
    assert result.value["password"] == "<SECRET>"
    assert "hunter2" not in str(result.vault)
    assert restore_mapping(result.value,result.vault).value["ssn"] == "not-even-a-valid-id"


def test_field_policy_secret_propagates_to_unlabeled_sibling():
    result=protect_mapping({"password":"hunter2","note":"hunter2"},Locator.preset("rules"),
                           field_types={("password",):"SECRET"})
    assert result.value == {"password":"<SECRET>","note":"<SECRET>"} and not result.vault


@pytest.mark.parametrize("value,policy",[({"id":123},{("id",):"GOV_ID"}),
    ({"id":"abc"},{("typo",):"GOV_ID"}),({"id":"abc"},{"id":"GOV_ID"})])
def test_bad_field_policy_fails_explicitly(value,policy):
    with pytest.raises(ValueError):protect_mapping(value,Locator.preset("rules"),field_types=policy)


def test_mapping_preserves_distinct_nonstring_keys_in_both_directions():
    from edgepii import mask_mapping
    source={1:"a@example.com","1":"b@example.com"}
    for masker in (mask_mapping,protect_mapping):
        result=masker(source,Locator.preset("rules"))
        assert len(result.value)==2 and set(result.value)==set(source)
        assert restore_mapping(result.value,result.vault).value==source


def test_a_literal_secret_placeholder_is_not_reused_as_its_own_redaction():
    source="<SECRET>"
    masked,vault=redact_protected(source,protection_plan(source,[span(source,"SECRET",0,len(source))]))
    assert masked != source and vault == {}
    assert restore(masked,vault).unresolved
