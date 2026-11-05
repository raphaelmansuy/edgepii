"""Verify the dated stage audits and retained protection-gate rejection."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from edgepii.eval.gates import GatePolicy, check_gates

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("stage_evidence_audit",ROOT/"modal/stage_audit.py")
stage=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
FILES=["spy-medical-multi-encoder-50-0bea79b7.json","spy-legal-multi-encoder-50-a6d83bcf.json",
       "spy-legal-en-closed-50-66c2f279.json"]


def audit():
    result={"stage_audits":[],"stage_audit_count":0}
    for filename in FILES:
        path=ROOT/"docs/eval/stages"/filename
        raw=path.read_bytes();data=json.loads(raw)
        assert data["provider"]=="modal" and data["first_principles_verification"]["contract_passed"]
        assert stage.summarize(data["cases"])==data["summary"]
        assert data["summary"]["documents"]==50
        def source_free(value):
            if isinstance(value,dict):
                assert not {"text","source","doc_id","claimed_text"}.intersection(value)
                for child in value.values():source_free(child)
            elif isinstance(value,list):
                for child in value:source_free(child)
        source_free(data["cases"])
        result["stage_audits"].append({"path":str(path.relative_to(ROOT)),"sha256":hashlib.sha256(raw).hexdigest(),
            "corpus":data["corpus"],"preset":data["preset"],"selection_sha256":data["selection_sha256"],
            "summary":data["summary"]})
    result["stage_audit_count"]=len(result["stage_audits"])
    path=ROOT/"docs/eval/modal/spy-medical-50-2a6ed546/spy-medical__multi-encoder-50.json"
    data=json.loads(path.read_text());row=data["slices"]["all"]
    assert data["gates"]==check_gates(data,GatePolicy(**data["gates"]["policy"]))
    assert not data["gates"]["passed"] and data["gates"]["policy"]["output"]=="protection"
    assert row["protection_plan"]["documents"]==50
    assert row["protection_plan"]["high_severity_leaking_documents"]==10
    assert row["high_severity_documents"]==39 and row["unmapped_predictions"]==234
    assert data["evaluation"]["selection_sha256"]==result["stage_audits"][0]["selection_sha256"]
    manifest=json.loads((path.parent/"run.json").read_text())
    assert manifest["state"]=="quality-gates-failed"
    result["readiness_gate"]={"path":str(path.relative_to(ROOT)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "expected_rejection":True,"gates":data["gates"],"protected_leaking_documents":row["protection_plan"]["high_severity_leaking_documents"]}
    path=ROOT/"docs/eval/modal/spy-legal-50-9cbb4e97/spy-legal__multi-encoder-50.json"
    historical=json.loads(path.read_text())
    legacy=check_gates(historical,GatePolicy(max_leaks=0))
    readiness=check_gates(historical,GatePolicy(max_leaks=0,output="protection"))
    assert legacy["passed"] and not readiness["passed"]
    result["historical_counterfactual"]={"path":str(path.relative_to(ROOT)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "scope":"re-gating saved measurements, no new inference or edited historical report",
        "selected_policy":legacy,"protection_readiness_policy":readiness}
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    args=parser.parse_args()
    result=audit()
    if args.out:Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("Verified three stage audits, expected readiness rejection, and historical counterfactual")
