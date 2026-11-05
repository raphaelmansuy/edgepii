"""Explicit release criteria. Empty or malformed reports cannot pass a gate."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GatePolicy:
    min_recall: float | None = None
    max_leaks: int | None = None
    max_dropped: int = 0

    def __post_init__(self):
        if self.min_recall is not None and not (
            math.isfinite(self.min_recall) and 0 <= self.min_recall <= 1
        ):
            raise ValueError("min_recall must be between zero and one")
        if self.max_leaks is not None and self.max_leaks < 0:
            raise ValueError("max_leaks must be nonnegative")
        if self.max_dropped < 0:
            raise ValueError("max_dropped must be nonnegative")


def check_gates(payload: dict, policy: GatePolicy) -> dict:
    """Apply criteria to every requested slice, including minority slices."""

    failures = []
    slices = payload.get("slices", {})
    if not slices:
        failures.append("report has no slices")
    if payload.get("corpus_diagnostics", {}).get("unknown_labels"):
        failures.append("corpus has unmapped gold labels")
    for name, row in slices.items():
        if row["documents"] <= 0:
            failures.append(f"{name}: no documents")
        if row["dropped_offsets"] > policy.max_dropped:
            failures.append(f"{name}: dropped offsets exceed {policy.max_dropped}")
        if policy.max_leaks is not None and row["high_severity_leaks"] > policy.max_leaks:
            failures.append(f"{name}: high severity leaks exceed {policy.max_leaks}")
        if policy.min_recall is not None:
            if row["gold_spans"] <= 0:
                failures.append(f"{name}: no gold spans for recall gate")
            elif not math.isfinite(row["recall"]) or row["recall"] < policy.min_recall:
                failures.append(f"{name}: recall below {policy.min_recall}")
    return {"passed": not failures, "policy": asdict(policy), "failures": failures}
