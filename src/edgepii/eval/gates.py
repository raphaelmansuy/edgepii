"""Explicit release criteria. Empty or malformed reports cannot pass a gate."""

from __future__ import annotations

import math
from dataclasses import dataclass


def _count(value):
    return type(value) is int and value >= 0


def _ratio(value):
    return type(value) in (int,float) and math.isfinite(value) and 0 <= value <= 1


@dataclass(frozen=True)
class GatePolicy:
    min_recall: float | None = None
    max_leaks: int | None = None
    max_dropped: int = 0
    output: str = "selected"
    min_containment: float | None = None
    min_masking_precision: float | None = None
    max_unmapped: int | None = None
    max_leaking_documents: int | None = None

    def __post_init__(self):
        for name in ("min_recall","min_containment","min_masking_precision"):
            value=getattr(self,name)
            if value is not None and not _ratio(value):
                raise ValueError(f"{name} must be between zero and one")
        for name in ("max_leaks","max_dropped","max_unmapped","max_leaking_documents"):
            value=getattr(self,name)
            if value is not None and not _count(value):
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.max_dropped is None:
            raise ValueError("max_dropped must be a nonnegative integer")
        if self.output not in {"selected","protection"}:
            raise ValueError("output must be selected or protection")

    def to_dict(self):
        # Preserve historical policy bytes when none of the new options is used.
        row={"min_recall":self.min_recall,"max_leaks":self.max_leaks,"max_dropped":self.max_dropped}
        if self.output != "selected":row["output"]=self.output
        for name in ("min_containment","min_masking_precision","max_unmapped","max_leaking_documents"):
            value=getattr(self,name)
            if value is not None:row[name]=value
        return row


def check_gates(payload: dict, policy: GatePolicy) -> dict:
    """Apply criteria to every requested slice, including minority slices."""

    failures = []
    slices = payload.get("slices", {})
    if not isinstance(slices,dict) or not slices:
        failures.append("report has no slices")
        slices={}
    if payload.get("corpus_diagnostics", {}).get("unknown_labels"):
        failures.append("corpus has unmapped gold labels")
    for name, row in slices.items():
        if not isinstance(row,dict):
            failures.append(f"{name}: malformed slice")
            continue
        docs=row.get("documents")
        if not _count(docs) or docs == 0:
            failures.append(f"{name}: no documents")
        if not _count(row.get("gold_spans")):
            failures.append(f"{name}: invalid gold spans count")
        dropped=row.get("dropped_offsets")
        if not _count(dropped):
            failures.append(f"{name}: invalid dropped offsets count")
        elif dropped > policy.max_dropped:
            failures.append(f"{name}: dropped offsets exceed {policy.max_dropped}")
        target=row
        coverage=row.get("containment")
        if policy.output=="protection":
            target=row.get("protection_plan")
            if not isinstance(target,dict) or not _count(target.get("documents")) or target.get("documents") != docs or not docs:
                failures.append(f"{name}: protection output unavailable or incomplete")
                target={}
            elif not _count(target.get("gold_spans")) or target.get("gold_spans") != row.get("gold_spans"):
                failures.append(f"{name}: protection gold count differs from slice")
            coverage=target
        leaks=target.get("high_severity_leaks")
        if not _count(leaks):
            failures.append(f"{name}: invalid high severity leaks count for {policy.output}")
        elif policy.max_leaks is not None and leaks > policy.max_leaks:
            failures.append(f"{name}: high severity leaks exceed {policy.max_leaks}")
        max_unmapped=policy.max_unmapped
        if policy.output=="protection" and max_unmapped is None:max_unmapped=0
        if max_unmapped is not None:
            unmapped=row.get("unmapped_predictions")
            if not _count(unmapped):
                failures.append(f"{name}: invalid unmapped predictions count")
            elif unmapped > max_unmapped:
                failures.append(f"{name}: unmapped predictions exceed {max_unmapped}")
        if policy.max_leaking_documents is not None:
            leaking=target.get("high_severity_leaking_documents")
            if not _count(leaking) or not _count(docs) or leaking > docs:
                failures.append(f"{name}: invalid high severity leaking documents count")
            elif leaking > policy.max_leaking_documents:
                failures.append(f"{name}: high severity leaking documents exceed {policy.max_leaking_documents}")
        if policy.min_recall is not None:
            if not _count(row.get("gold_spans")) or row["gold_spans"] == 0:
                failures.append(f"{name}: no gold spans for recall gate")
            elif not _ratio(row.get("recall")) or row["recall"] < policy.min_recall:
                failures.append(f"{name}: recall below {policy.min_recall}")
        for field,minimum in (("span_recall",policy.min_containment),("masking_precision",policy.min_masking_precision)):
            if minimum is None:continue
            if not isinstance(coverage,dict) or not _ratio(coverage.get(field)):
                failures.append(f"{name}: {field} unavailable or invalid for {policy.output}")
            elif field=="span_recall" and (not _count(row.get("gold_spans")) or row["gold_spans"]==0):
                failures.append(f"{name}: no gold spans for containment gate")
            elif coverage[field] < minimum:
                failures.append(f"{name}: {field} below {minimum}")
    return {"passed": not failures, "policy": policy.to_dict(), "failures": failures}
