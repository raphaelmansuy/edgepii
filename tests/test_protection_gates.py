"""Gate the emitted path using an actual masking counterexample and bad reports."""

import copy
import json
from types import SimpleNamespace

import pytest

from edgepii import Locator
from edgepii.eval.corpora import Doc
from edgepii.eval.gates import GatePolicy, check_gates
from edgepii.eval.runner import score_docs
from edgepii.protocol import Hit


def report():
    class Detector:
        def locate(self,source,labels):
            return [Hit("PERSON",0,10,.9,"model"),Hit("SECRET",4,6,1.,"model")]
    locator=Locator.from_detectors([Detector()])
    score=score_docs(locator,[Doc("1","abcdefghij",(),(("GOV_ID",0,10),))],"all",set(locator.taxonomy.default_types()))
    return {"slices":{"all":score.to_dict()}}


def test_actual_protected_mask_passes_when_selected_typed_span_leaks():
    payload=report()
    row=payload["slices"]["all"]
    assert row["high_severity_leaks"]==row["high_severity_leaking_documents"]==1
    assert row["protection_plan"]["high_severity_leaks"]==0
    assert row["protection_plan"]["high_severity_leaking_documents"]==0
    assert not check_gates(payload,GatePolicy(max_leaks=0))["passed"]
    assert check_gates(payload,GatePolicy(max_leaks=0,output="protection",min_containment=1,
                                        min_masking_precision=1,max_leaking_documents=0))["passed"]


def test_protection_gate_rejects_unmapped_diagnostics_by_default():
    payload=report()
    payload["slices"]["all"]["unmapped_predictions"]=1
    assert not check_gates(payload,GatePolicy(output="protection"))["passed"]
    assert check_gates(payload,GatePolicy(output="protection",max_unmapped=1))["passed"]


@pytest.mark.parametrize("change", [
    {"documents":0},{"documents":2},{"gold_spans":0},
    {"high_severity_leaks":None},{"high_severity_leaks":float("nan")},
    {"high_severity_leaks":-1},{"high_severity_leaks":True},
    {"span_recall":None},{"span_recall":float("nan")},
    {"masking_precision":None},{"masking_precision":1.1},
    {"high_severity_leaking_documents":2},
])
def test_unavailable_partial_or_invalid_protection_metrics_fail_closed(change):
    payload=report()
    payload["slices"]["all"]["protection_plan"].update(change)
    result=check_gates(payload,GatePolicy(output="protection",max_leaks=0,min_containment=0,
                                        min_masking_precision=0,max_leaking_documents=1))
    assert not result["passed"]


def test_native_experiment_cannot_claim_public_protection_readiness():
    payload=report()
    payload["slices"]["all"].pop("protection_plan")
    assert not check_gates(payload,GatePolicy(output="protection"))["passed"]


def test_minority_slice_has_its_own_protection_criteria():
    payload=report()
    payload["slices"]["minority"]=copy.deepcopy(payload["slices"]["all"])
    payload["slices"]["minority"]["protection_plan"]["span_recall"]=.5
    result=check_gates(payload,GatePolicy(output="protection",min_containment=.9))
    assert result["failures"]==["minority: span_recall below 0.9"]


@pytest.mark.parametrize("kwargs", [
    {"output":"native"},{"max_leaks":float("nan")},{"max_leaks":1.5},
    {"max_unmapped":-1},{"max_leaking_documents":True},{"min_containment":float("nan")},
    {"min_masking_precision":1.1},{"min_recall":True},
])
def test_invalid_thresholds_are_rejected(kwargs):
    with pytest.raises(ValueError):GatePolicy(**kwargs)


def test_historical_default_policy_serialization_is_stable():
    assert GatePolicy().to_dict()=={"min_recall":None,"max_leaks":None,"max_dropped":0}
    assert check_gates(report(),GatePolicy())["policy"]==GatePolicy().to_dict()


def test_cli_saves_protection_failures_and_records_the_selected_gate_path(monkeypatch,tmp_path):
    from edgepii.eval import cli
    payload=report()
    payload["slices"]["all"]["unmapped_predictions"]=1
    monkeypatch.setattr(cli,"score_corpus",lambda *a,**k:SimpleNamespace(to_dict=lambda:payload))
    path=tmp_path/"gated.json"
    assert cli.main(["--corpus","gretel-finance-en","--gate-output","protection",
                     "--max-leaks","0","--max-leaking-documents","0","--out",str(path)])==1
    saved=json.loads(path.read_text())
    assert saved["gates"]["policy"]["output"]=="protection"
    assert saved["gates"]["failures"]==["all: unmapped predictions exceed 0"]
