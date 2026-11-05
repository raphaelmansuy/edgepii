"""Verify the distributed package from an isolated interpreter, without models.

Run: /path/to/clean/venv/bin/python -I scripts/verify_install.py --version 0.5.0
"""

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Expected installed release version")
    args = parser.parse_args()

    import edgepii
    from edgepii import (
        IncompleteDetectionError, Locator, ProtectionPlan, protect_mapping,
        protection_plan, redact_protected, restore, restore_mapping,
    )

    installed = importlib.metadata.version("edgepii")
    assert edgepii.__version__ == installed
    if args.version:
        assert installed == args.version, "installed version mismatch"
    assert "site-packages" in Path(edgepii.__file__).parts, "source checkout imported"

    source = "🛡️ Contact ada@example.com. Card 4242424242424242."
    locator = Locator.preset("rules")
    located = locator.locate(source)
    assert all(source[s.start:s.end] == s.text for s in located.spans)
    assert {s.type for s in located.spans} >= {"EMAIL", "PAYMENT"}
    plan = locator.plan(source)
    assert isinstance(plan, ProtectionPlan)
    masked, vault = redact_protected(source, plan)
    assert "ada@example.com" not in masked and "4242424242424242" not in masked
    assert restore(masked, vault).text == source
    try:
        redact_protected(source + "!", plan)
    except ValueError:
        pass
    else:
        raise AssertionError("plan accepted a different source")
    try:
        protection_plan(source, (), dropped=1)
    except IncompleteDetectionError:
        pass
    else:
        raise AssertionError("strict plan accepted incomplete detection")

    args_tree = {"password": "hunter2", "note": "hunter2", "email": "ada@example.com"}
    protected = protect_mapping(args_tree, locator, field_types={("password",): "SECRET"})
    assert protected.value["password"] == protected.value["note"] == "<SECRET>"
    assert "hunter2" not in str(protected.vault)
    assert restore_mapping(protected.value, protected.vault).value["email"] == args_tree["email"]
    assert protected.changed
    assert "GOV_ID" in {s.type for s in Locator.preset("rules-us").locate("SSN: 123-45-6789").spans}
    assert not Locator.preset("rules").locate("SSN: 123-45-6789").spans
    assert "torch" not in sys.modules, "rules imported an optional model runtime"
    checks = [
        "installed distribution", "public exports", "Unicode source offsets",
        "mask/restore round trip", "source binding", "strict diagnostics",
        "explicit field policy", "cross-leaf secret irreversibility",
        "country profile opt-in", "no Torch import",
    ]
    if tuple(map(int,installed.split(".")[:2])) >= (0,5):
        from edgepii.eval.corpora import Doc
        from edgepii.eval.gates import GatePolicy, check_gates
        from edgepii.eval.runner import score_docs
        from edgepii.protocol import Hit
        class Injected:
            def locate(self,text,labels):
                return [Hit("PERSON",0,10,.9,"fixture"),Hit("SECRET",4,6,1.,"fixture")]
        injected=Locator.from_detectors([Injected()])
        row=score_docs(injected,[Doc("1","abcdefghij",(),(("GOV_ID",0,10),))],"all",set(injected.taxonomy.default_types())).to_dict()
        payload={"slices":{"all":row}}
        assert not check_gates(payload,GatePolicy(max_leaks=0))["passed"]
        assert check_gates(payload,GatePolicy(output="protection",max_leaks=0,min_containment=1,max_leaking_documents=0))["passed"]
        row["unmapped_predictions"]=1
        assert not check_gates(payload,GatePolicy(output="protection",max_leaks=0))["passed"]
        checks += ["emitted protection gate path", "unmapped protection readiness rejection"]
    assert "torch" not in sys.modules
    print(json.dumps({"passed": True, "version": installed, "checks":checks},sort_keys=True))


if __name__ == "__main__":
    main()
