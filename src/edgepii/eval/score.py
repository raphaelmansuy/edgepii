"""Exact-span F1. A match needs the same type, the same start, and the same end."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TypeScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    f2: float = 0.0


@dataclass
class ScoreReport:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    f2: float
    miss: int
    wrong_type: int
    shift: int
    extra: int
    per_type: dict[str, TypeScore] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "f2": self.f2,
            "miss": self.miss,
            "wrong_type": self.wrong_type,
            "shift": self.shift,
            "extra": self.extra,
            "per_type": {
                name: {
                    "tp": row.tp,
                    "fp": row.fp,
                    "fn": row.fn,
                    "precision": row.precision,
                    "recall": row.recall,
                    "f1": row.f1,
                    "f2": row.f2,
                }
                for name, row in self.per_type.items()
            },
        }


def exact_span_f1(gold: list, pred: list) -> ScoreReport:
    gold_rows = [_triple(item) for item in gold]
    pred_rows = [_triple(item) for item in pred]
    return _score(gold_rows, pred_rows, with_types=True)


def _score(
    gold_rows: list[tuple[str, int, int]],
    pred_rows: list[tuple[str, int, int]],
    with_types: bool,
) -> ScoreReport:
    matched_gold: set[int] = set()
    matched_pred: set[int] = set()
    for g_index, g_row in enumerate(gold_rows):
        for p_index, p_row in enumerate(pred_rows):
            if p_index in matched_pred:
                continue
            if g_row == p_row:
                matched_gold.add(g_index)
                matched_pred.add(p_index)
                break
    miss = 0
    wrong_type = 0
    shift = 0
    for g_index, g_row in enumerate(gold_rows):
        if g_index in matched_gold:
            continue
        overlaps = [
            p_row
            for p_index, p_row in enumerate(pred_rows)
            if p_index not in matched_pred and _overlap(g_row, p_row)
        ]
        if any(p_row[0] == g_row[0] for p_row in overlaps):
            shift += 1
        elif overlaps:
            wrong_type += 1
        else:
            miss += 1
    extra = 0
    for p_index, p_row in enumerate(pred_rows):
        if p_index in matched_pred:
            continue
        if not any(_overlap(g_row, p_row) for g_row in gold_rows):
            extra += 1
    tp = len(matched_gold)
    fp = len(pred_rows) - tp
    fn = len(gold_rows) - tp
    precision, recall, f1, f2 = _prf(tp, fp, fn)
    per_type = _per_type(gold_rows, pred_rows) if with_types else {}
    return ScoreReport(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        f2=f2,
        miss=miss,
        wrong_type=wrong_type,
        shift=shift,
        extra=extra,
        per_type=per_type,
    )


def leakage_count(gold: list, predicted: list, high_types: set[str]) -> int:
    """Count high-severity gold spans that a prediction does not fully cover."""

    leaks = 0
    preds = [_triple(item) for item in predicted]
    for item in gold:
        row = _triple(item)
        if row[0] not in high_types:
            continue
        if not _fully_covered(row, preds):
            leaks += 1
    return leaks


def _triple(item) -> tuple[str, int, int]:
    if isinstance(item, tuple):
        return item[0], int(item[1]), int(item[2])
    return item.type, int(item.start), int(item.end)


def _overlap(left: tuple[str, int, int], right: tuple[str, int, int]) -> bool:
    return left[1] < right[2] and right[1] < left[2]


def _fully_covered(gold: tuple[str, int, int], preds: list[tuple[str, int, int]]) -> bool:
    start, end = gold[1], gold[2]
    if end <= start:
        return True
    flags = [False] * (end - start)
    for _type, pred_start, pred_end in preds:
        lo = max(start, pred_start)
        hi = min(end, pred_end)
        for index in range(lo, hi):
            flags[index - start] = True
    return all(flags)


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float, float]:
    precision = 1.0 if tp + fp == 0 else tp / (tp + fp)
    recall = 1.0 if tp + fn == 0 else tp / (tp + fn)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    beta2 = 4.0
    denom = beta2 * precision + recall
    f2 = 0.0 if denom == 0 else (1 + beta2) * precision * recall / denom
    return precision, recall, f1, f2


def _per_type(gold: list[tuple[str, int, int]], pred: list[tuple[str, int, int]]) -> dict[str, TypeScore]:
    names = sorted({row[0] for row in gold} | {row[0] for row in pred})
    rows: dict[str, TypeScore] = {}
    for name in names:
        g_rows = [row for row in gold if row[0] == name]
        p_rows = [row for row in pred if row[0] == name]
        report = _score(g_rows, p_rows, with_types=False)
        rows[name] = TypeScore(
            tp=report.tp,
            fp=report.fp,
            fn=report.fn,
            precision=report.precision,
            recall=report.recall,
            f1=report.f1,
            f2=report.f2,
        )
    return rows
