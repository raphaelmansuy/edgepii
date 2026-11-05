"""Recompute saved paired outcomes and check matched Modal experiment evidence."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("paired_audit",ROOT/"modal/paired_metrics.py")
paired=importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
FOLDERS=["spy-legal-50-5fdf7be4","spy-medical-50-55290bac",
         "gretel-finance-en-50-9418dddc","spy-medical-50-733d5cc0"]
PAIRED_FILES=["spy-medical-50-complementarity-2f132a4b.json",
              "gretel-finance-en-50-complementarity-bcd3f281.json",
              "spy-medical-50-quantized-f59f4ca4.json",
              "gretel-finance-en-50-quantized-449da1bc.json"]


def audit():
    result={"scope":"exploratory native containment; integration passes are not zero-leak promotion",
            "reports":[],"paired":[],"report_count":0,"paired_count":0}
    selections={}
    for folder in FOLDERS:
        directory=ROOT/"docs/eval/modal"/folder
        manifest=json.loads((directory/"run.json").read_text())
        assert manifest["state"]=="complete"
        assert len(manifest["completed"])==len(manifest["requested_presets"])==4
        for item in manifest["completed"]:
            path=directory/item["report"]
            raw=path.read_bytes()
            report=json.loads(raw)
            assert report["runtime"]["provider"]=="modal"
            assert report["first_principles_verification"]["contract_passed"]
            assert report["gates"]["passed"]
            assert "recall" not in report["slices"]["all"]
            digest=report["evaluation"]["selection_sha256"]
            assert selections.setdefault(report["corpus"],digest)==digest
            row=report["slices"]["all"]
            assert row["documents"]==50 and row["dropped_offsets"]==0
            result["reports"].append({"path":str(path.relative_to(ROOT)),"sha256":hashlib.sha256(raw).hexdigest(),
                "corpus":report["corpus"],"preset":report["preset"],"revision":report["preset_revision"],
                "device":report["runtime"]["device"],"selection_sha256":digest,
                "gold_spans":row["gold_spans"],"high_severity_misses":row["high_severity_leaks"],
                "containment":row["containment"],"p95_ms":report["latency_ms"]["p95"],
                "gpu_allocated_bytes":report["runtime"]["peak_gpu_allocated_bytes"],
                "process_peak_rss_bytes":report["runtime"]["process_peak_rss_bytes"]})
    # A later reproduction adds files; it must not change this dated audit set.
    for path in (ROOT/"docs/eval/paired"/name for name in sorted(PAIRED_FILES)):
        raw=path.read_bytes()
        report=json.loads(raw)
        assert report["provider"]=="modal" and report["first_principles_verification"]["contract_passed"]
        assert report["selection_sha256"]==selections[report["corpus"]]
        assert paired.summarize(report["cases"])==report["summary"]
        assert len(report["cases"])==50
        forbidden={"source","text","doc_id","claimed_text"}
        def inspect(value):
            if isinstance(value,dict):
                assert not forbidden.intersection(value)
                for child in value.values():inspect(child)
            elif isinstance(value,list):
                for child in value:inspect(child)
        inspect(report["cases"])
        result["paired"].append({"path":str(path.relative_to(ROOT)),"sha256":hashlib.sha256(raw).hexdigest(),
            "corpus":report["corpus"],"quantized":report["quantized"],"selection_sha256":report["selection_sha256"],
            "summary":report["summary"],"single_span_support_counts":report["single_span_support_counts"]})
    result["report_count"]=len(result["reports"])
    result["paired_count"]=len(result["paired"])
    result["runtime_precision"]=[]
    for filename in ("compact-runtime-precision-2026-11-05.json",
                     "compact-runtime-precision-cpu-2026-11-05.json"):
        path=ROOT/"docs/research"/filename
        probe=json.loads(path.read_text())
        assert probe["provider"]=="modal" and probe["mode"]=="runtime-inspection"
        actual={r["preset"]:r["actual_parameter_dtype"] for r in probe["models"]}
        assert actual=={"ettin-native":"torch.bfloat16","horizon-native":"torch.float32",
                        "masker-mini-native":"torch.float32"}
        result["runtime_precision"].append({"path":str(path.relative_to(ROOT)),
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"models":probe["models"]})
    assert result["report_count"]==16 and result["paired_count"]==4
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    args=parser.parse_args()
    result=audit()
    if args.out:
        Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("Verified",result["report_count"],"matched reports and",result["paired_count"],"recomputed paired experiments")
