"""Audit completed model experiments without treating quality failures as passes."""

import json
from pathlib import Path

from edgepii.eval.gates import GatePolicy, check_gates


def audit(root=Path("docs/eval/modal")):
    summary = {"completed_runs": [], "failed_runs": [], "reports_checked": 0,
               "reports_failing_zero_leak_policy": 0, "integration_gate_failures": []}
    for path in sorted(root.glob("*/run.json")):
        manifest = json.loads(path.read_text())
        if manifest["state"] not in {"complete", "quality-gates-failed"}:
            summary["failed_runs"].append({"run": path.parent.name, "state": manifest["state"]})
            continue
        assert set(manifest["requested_presets"]) == {row["preset"] for row in manifest["completed"]}
        selections = set()
        any_failed = False
        for row in manifest["completed"]:
            report_path = path.parent / row["report"]
            assert report_path.resolve().is_relative_to(path.parent.resolve())
            report = json.loads(report_path.read_text())
            assert report["preset"] == row["preset"]
            assert report["runtime"]["provider"] == "modal"
            assert report["first_principles_verification"]["contract_passed"]
            assert report["latency_ms"]["calls"] == report["evaluation"]["unique_documents"]
            selections.add(report["evaluation"]["selection_sha256"])
            if "model_only_ablation" in report:
                assert report["model_only_ablation"]["evaluation"]["selection_sha256"] in selections
            actual = check_gates(report, GatePolicy(**report["gates"]["policy"]))
            assert actual == report["gates"]
            assert actual["passed"] == row["gates_passed"]
            summary["reports_checked"] += 1
            if not actual["passed"]:
                any_failed = True
                summary["integration_gate_failures"].append({"report": str(report_path), "failures": actual["failures"]})
            if not check_gates(report, GatePolicy(max_leaks=0))["passed"]:
                summary["reports_failing_zero_leak_policy"] += 1
        assert len(selections) == 1, "a completed tournament mixed evaluation inputs"
        assert manifest["state"] == ("quality-gates-failed" if any_failed else "complete")
        summary["completed_runs"].append(path.parent.name)
    assert summary["reports_checked"] > 0, "no completed experiments to audit"
    return summary


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
