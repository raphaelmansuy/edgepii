"""Score an edgepii preset on a pinned public PII corpus.

    python -m edgepii.eval.cli --preset rules --corpus nemotron-pii
    python -m edgepii.eval.cli --preset rules --corpus gretel-finance-en --limit 500

The run reads the pin from `corpora.yaml`, checks the sha256, scores every
document, and writes one JSON report. The report holds counts, not source text.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

from edgepii.eval.corpora import CorpusError, corpus_keys, load_spec
from edgepii.eval.runner import score_corpus
from edgepii.eval.gates import GatePolicy, check_gates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edgepii.eval")
    parser.add_argument("--preset", default="rules", help="preset name, for example rules")
    parser.add_argument("--corpus", required=True, help="corpus key, for example nemotron-pii")
    parser.add_argument("--limit", type=int, default=None, help="take the first N documents of each slice")
    parser.add_argument("--slice", action="append", dest="slices", default=None, help="slice name. repeatable")
    parser.add_argument("--types", default=None, help="comma separated type subset")
    parser.add_argument("--cache", default=None, help="corpus cache directory")
    parser.add_argument("--out", default=None, help="report path. default is a name in docs/eval")
    parser.add_argument("--device", default="cpu", help="torch device for a model preset")
    parser.add_argument("--print", action="store_true", dest="show", help="print the table too")
    parser.add_argument("--min-score", type=float, default=None, help="caller score floor")
    parser.add_argument("--min-recall", type=float, default=None, help="minimum recall in every slice")
    parser.add_argument("--max-leaks", type=int, default=None, help="maximum high severity leaks per slice")
    parser.add_argument("--max-dropped", type=int, default=0, help="maximum invalid offsets per slice")
    parser.add_argument("--gate-output", choices=("selected","protection"), default="selected",
                        help="output whose leakage/containment/precision is gated")
    parser.add_argument("--min-containment",type=float,default=None,help="minimum complete-span containment per slice")
    parser.add_argument("--min-masking-precision",type=float,default=None,help="minimum covered-gold/masked character ratio")
    parser.add_argument("--max-unmapped",type=int,default=None,help="maximum unmapped predictions; protection defaults to zero")
    parser.add_argument("--max-leaking-documents",type=int,default=None,help="maximum documents with a high-severity miss per slice")
    args = parser.parse_args(argv)
    try:
        policy = GatePolicy(args.min_recall,args.max_leaks,args.max_dropped,output=args.gate_output,
            min_containment=args.min_containment,min_masking_precision=args.min_masking_precision,
            max_unmapped=args.max_unmapped,max_leaking_documents=args.max_leaking_documents)
        if args.limit is not None and args.limit <= 0:
            raise ValueError("limit must be positive")
        if args.min_score is not None and not (math.isfinite(args.min_score) and 0 <= args.min_score <= 1):
            raise ValueError("min_score must be between zero and one")
    except ValueError as exc:
        parser.error(str(exc))

    from edgepii import DetectorLoadError, Locator

    cache = Path(args.cache) if args.cache else _default_cache()
    types = [name.strip() for name in args.types.split(",")] if args.types else None
    try:
        locator = Locator.preset(args.preset, device=args.device)
        report = score_corpus(
            locator,
            corpus=args.corpus,
            cache_dir=cache,
            limit=args.limit,
            slices=args.slices,
            types=types,
            min_score=args.min_score,
        )
    except (CorpusError, DetectorLoadError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = report.to_dict()
    payload["gates"] = check_gates(payload, policy)
    out = Path(args.out) if args.out else _default_report(args.preset, args.corpus, args.limit)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.show:
        print(table(payload))
    print(f"wrote {out}", file=sys.stderr)
    for failure in payload["gates"]["failures"]:
        print(f"gate failed: {failure}", file=sys.stderr)
    return 0 if payload["gates"]["passed"] else 1


def table(payload: dict) -> str:
    lines = [
        f"preset={payload['preset']} revision={payload['preset_revision'][:12]} "
        f"corpus={payload['corpus']}@{payload['corpus_revision'][:12]} "
        f"taxonomy={payload['taxonomy_version']} limit={payload['document_limit']}"
    ]
    header = f"{'slice':13} {'docs':>6} {'gold':>6} {'pred':>6} {'tp':>6} {'fp':>5} {'fn':>5} {'P':>6} {'R':>6} {'F1':>6} {'F2':>6} {'leak':>4}"
    lines.append(header)
    if payload.get("gates",{}).get("policy",{}).get("output")=="protection":
        lines.insert(1,"gate output=protection; table below shows selected typed spans")
    for name, row in payload["slices"].items():
        lines.append(
            f"{name:13} {row['documents']:6d} {row['gold_spans']:6d} {row['predicted_spans']:6d} "
            f"{row['tp']:6d} {row['fp']:5d} {row['fn']:5d} "
            f"{row['precision']:6.3f} {row['recall']:6.3f} {row['f1']:6.3f} {row['f2']:6.3f} "
            f"{row['high_severity_leaks']:4d}"
        )
    diagnostics = payload["corpus_diagnostics"]
    if diagnostics["unknown_labels"]:
        lines.append(f"unknown gold labels: {diagnostics['unknown_labels']}")
    lines.append("")
    lines.append("per type, slice 'all':")
    for name, row in payload["slices"].get("all", {}).get("per_type", {}).items():
        lines.append(
            f"  {name:13} tp={row['tp']:5d} fp={row['fp']:5d} fn={row['fn']:5d} "
            f"P={row['precision']:.3f} R={row['recall']:.3f} F1={row['f1']:.3f}"
        )
    return "\n".join(lines)


def _default_cache() -> Path:
    override = os.environ.get("EDGEPII_CACHE")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "edgepii"


def _default_report(preset: str, corpus: str, limit: int | None) -> Path:
    suffix = f"-{limit}" if limit else "-full"
    return Path("docs/eval") / f"{corpus}__{preset}{suffix}.json"


if __name__ == "__main__":
    raise SystemExit(main())
