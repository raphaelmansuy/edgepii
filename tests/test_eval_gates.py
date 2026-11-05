"""Release gates must expose regressions, empty runs, and selection changes."""

import json
from types import SimpleNamespace

import pytest

from edgepii import Locator
from edgepii.eval import runner
from edgepii.eval.corpora import Doc, GoldDiagnostics
from edgepii.eval.gates import GatePolicy, check_gates


def payload():
    return {"slices": {"all": {"documents": 1, "gold_spans": 1, "recall": 1.0,
                              "dropped_offsets": 0, "high_severity_leaks": 0}}}


def test_gates_fail_on_a_minority_slice_even_when_overall_recall_passes():
    report = payload()
    report["slices"]["minority"] = dict(report["slices"]["all"], recall=0.1)
    result = check_gates(report, GatePolicy(min_recall=0.9))
    assert not result["passed"]
    assert result["failures"] == ["minority: recall below 0.9"]


@pytest.mark.parametrize("field,value,policy", [
    ("documents", 0, GatePolicy()),
    ("gold_spans", 0, GatePolicy(min_recall=0.5)),
    ("dropped_offsets", 1, GatePolicy()),
    ("high_severity_leaks", 1, GatePolicy(max_leaks=0)),
    ("recall", float("nan"), GatePolicy(min_recall=0.5)),
])
def test_a_bad_result_cannot_pass(field, value, policy):
    report = payload()
    report["slices"]["all"][field] = value
    assert not check_gates(report, policy)["passed"]


def test_empty_report_and_unmapped_gold_cannot_pass():
    assert not check_gates({"slices": {}}, GatePolicy())["passed"]
    report = payload()
    report["corpus_diagnostics"] = {"unknown_labels": {"new_label": 2}}
    assert not check_gates(report, GatePolicy())["passed"]


@pytest.mark.parametrize("kwargs", [{"min_recall": -1}, {"min_recall": float("nan")},
                                   {"min_recall": 2}, {"max_leaks": -1}, {"max_dropped": -1}])
def test_invalid_policy_is_rejected(kwargs):
    with pytest.raises(ValueError):
        GatePolicy(**kwargs)


def test_matched_evaluations_fingerprint_inputs_without_storing_them(monkeypatch, tmp_path):
    docs = [Doc("1", "ada@example.com", (), (("EMAIL", 0, 15),))]
    monkeypatch.setattr(runner, "ensure_file", lambda *a: tmp_path / "unused")
    monkeypatch.setattr(runner, "read_raw", lambda *a: [])
    monkeypatch.setattr(runner, "build_docs", lambda *a: (docs, GoldDiagnostics()))
    locator = Locator.preset("rules")

    def run():
        return runner.score_corpus(locator, "gretel-finance-en", tmp_path,
                                   slices=["all"], types=["EMAIL"], limit=1).to_dict()

    first = run()
    assert first["evaluation"]["selection_sha256"] == run()["evaluation"]["selection_sha256"]
    assert first["evaluation"]["types"] == ["EMAIL"]
    assert first["evaluation"]["unique_documents"] == first["latency_ms"]["calls"] == 1
    assert first["latency_ms"]["p50"] <= first["latency_ms"]["p95"]
    assert "ada@example.com" not in json.dumps(first)
    docs[0] = Doc("2", "bob@example.com", (), (("EMAIL", 0, 15),))
    assert first["evaluation"]["selection_sha256"] != run()["evaluation"]["selection_sha256"]


def test_cli_persists_failed_report_and_returns_nonzero(monkeypatch, tmp_path):
    from edgepii.eval import cli

    report = payload()
    report["slices"]["all"]["high_severity_leaks"] = 1
    monkeypatch.setattr(cli, "score_corpus", lambda *a, **k: SimpleNamespace(to_dict=lambda: report))
    path = tmp_path / "failed.json"
    assert cli.main(["--corpus", "gretel-finance-en", "--max-leaks", "0", "--out", str(path)]) == 1
    saved = json.loads(path.read_text())
    assert not saved["gates"]["passed"]
    assert saved["gates"]["policy"]["max_leaks"] == 0


def test_zero_document_limit_is_rejected_before_loading_a_model():
    from edgepii.eval.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--corpus", "gretel-finance-en", "--limit", "0"])
    assert exc.value.code == 2
