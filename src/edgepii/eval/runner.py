"""Score a preset on a public corpus. One JSON report per run.

The report holds no source text. It holds counts, the corpus pin, the preset
pin, and the taxonomy version, so a second person can replay the run.

Exact-span F1 is computed per document and then summed. A pooled list of every
gold span in the corpus is not the same score: a span that repeats in two
documents could match across the document boundary.
"""

from __future__ import annotations

import platform
import time
from dataclasses import dataclass, field
from pathlib import Path

from edgepii.eval.corpora import (
    build_docs,
    ensure_file,
    label_audit,
    load_spec,
    materialize_spy,
    read_raw,
)

# The official SPY loader seeds Faker. A fixed seed makes a rerun identical.
SPY_SEED = 42

from edgepii.eval.score import TypeScore, leakage_count

# A gold span in one of these classes must not survive redact. See ADR 0004 and
# docs/09-evaluation.md.
HIGH_SEVERITY = {"secret", "gov_id", "payment"}


@dataclass(slots=True)
class SliceScore:
    name: str
    docs: int = 0
    gold: int = 0
    pred: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    miss: int = 0
    wrong_type: int = 0
    shift: int = 0
    extra: int = 0
    leaks: int = 0
    dropped: int = 0
    per_type: dict[str, TypeScore] = field(default_factory=dict)

    def finish(self) -> None:
        """Turn the accumulated counts into the four ratios, once per type."""

        for row in self.per_type.values():
            row.precision, row.recall, row.f1, row.f2 = _prf(row.tp, row.fp, row.fn)

    def to_dict(self) -> dict:
        precision, recall, f1, f2 = _prf(self.tp, self.fp, self.fn)
        return {
            "slice": self.name,
            "documents": self.docs,
            "gold_spans": self.gold,
            "predicted_spans": self.pred,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "f2": f2,
            "miss": self.miss,
            "wrong_type": self.wrong_type,
            "shift": self.shift,
            "extra": self.extra,
            "high_severity_leaks": self.leaks,
            "dropped_offsets": self.dropped,
            "per_type": {
                name: _type_dict(row) for name, row in sorted(self.per_type.items())
            },
        }


@dataclass(slots=True)
class RunReport:
    preset: str
    revision: str
    taxonomy_version: str
    corpus: str
    corpus_revision: str
    corpus_sha256: str
    corpus_license: str
    limit: int | None
    diagnostics: dict
    slices: dict[str, SliceScore]
    seconds: float
    environment: dict

    def to_dict(self) -> dict:
        return {
            "preset": self.preset,
            "preset_revision": self.revision,
            "taxonomy_version": self.taxonomy_version,
            "corpus": self.corpus,
            "corpus_revision": self.corpus_revision,
            "corpus_sha256": self.corpus_sha256,
            "corpus_license": self.corpus_license,
            "document_limit": self.limit,
            "documents_scored": sum(row.docs for name, row in self.slices.items() if name == "all"),
            "corpus_diagnostics": self.diagnostics,
            "corpus_diagnostics_scope": "whole file, not the limited run",
            "seconds": round(self.seconds, 3),
            "environment": self.environment,
            "slices": {name: row.to_dict() for name, row in sorted(self.slices.items())},
        }


def score_corpus(
    locator,
    corpus: str,
    cache_dir: Path,
    limit: int | None = None,
    slices: list[str] | None = None,
    types: list[str] | None = None,
) -> RunReport:
    """Score one corpus. `limit` is a prefix per slice, not per corpus.

    A per-slice prefix matters because a corpus can hold its locales in blocks.
    A corpus-wide prefix of 500 would read only the `us` block of Nemotron-PII
    and report an empty `intl` slice.
    """

    spec = load_spec(corpus)
    known = set(locator.taxonomy.types)
    problems = label_audit(spec, known)
    if problems:
        raise RuntimeError(f"label map for {corpus} is not valid: {problems}")
    requested = list(types) if types is not None else locator.taxonomy.default_types()
    for name in requested:
        locator.taxonomy.require(name)
    allowed = set(requested)
    names = list(slices) if slices else ["all", *sorted(spec.slices)]
    for name in names:
        if name != "all" and name not in spec.slices:
            raise RuntimeError(f"corpus {corpus} has no slice {name}")

    path = ensure_file(spec, cache_dir)
    records = read_raw(path)
    # A corpus of templates needs one materialisation step before scoring. The
    # seed is fixed, so a rerun reads the same values.
    if spec.spans_encoding == "bio":
        records = materialize_spy(records, seed=SPY_SEED)
    docs, diagnostics = build_docs(records, spec, allowed)

    # One pass over the documents. Each document feeds every slice it belongs to,
    # so a run with four slices does not call the locator four times per document.
    report_slices: dict[str, SliceScore] = {name: SliceScore(name=name) for name in names}
    membership = _slice_membership(spec, names, docs)
    selected = _selected_docs(membership, limit)
    started = time.perf_counter()
    for index, doc in enumerate(docs):
        if index not in selected:
            continue
        result = locator.locate(doc.text, types=sorted(allowed))
        pred = [(span.type, span.start, span.end) for span in result.spans]
        for name in selected[index]:
            _accumulate(report_slices[name], locator, doc, pred, result.dropped)
    for row in report_slices.values():
        row.finish()
    seconds = time.perf_counter() - started

    return RunReport(
        preset=locator.preset_name,
        revision=locator.revision,
        taxonomy_version=locator.taxonomy.version,
        corpus=spec.key,
        corpus_revision=spec.revision,
        corpus_sha256=spec.sha256,
        corpus_license=spec.license,
        limit=limit,
        diagnostics=diagnostics.to_dict(),
        slices=report_slices,
        seconds=seconds,
        environment=_environment(locator),
    )


def _selected_docs(membership: dict[int, list[str]], limit: int | None) -> dict[int, list[str]]:
    """Keep a prefix of each slice. A document serves only the slices that kept it."""

    if limit is None:
        return membership
    counts: dict[str, int] = {}
    selected: dict[int, list[str]] = {}
    for index in sorted(membership):
        kept = [
            name
            for name in membership[index]
            if counts.get(name, 0) < limit
        ]
        if not kept:
            continue
        for name in kept:
            counts[name] = counts.get(name, 0) + 1
        selected[index] = kept
    return selected


def score_docs(
    locator,
    docs,
    name: str,
    allowed: set[str],
    min_score: float | None = None,
) -> SliceScore:
    """Score a fixed list of documents. The test seam, and the single-doc path.

    `min_score` is caller policy, passed straight to `locate`. A sweep over
    floors calls this function once per floor, so a reader can see what a floor
    costs instead of reading four identical rows.
    """

    out = SliceScore(name=name)
    ordered = sorted(allowed)
    for doc in docs:
        result = locator.locate(doc.text, types=ordered, min_score=min_score)
        pred = [(span.type, span.start, span.end) for span in result.spans]
        _accumulate(out, locator, doc, pred, result.dropped)
    out.finish()
    return out


def _slice_membership(spec, names: list[str], docs) -> dict[int, list[str]]:
    """Which slices each document belongs to. `all` holds every document."""

    membership: dict[int, list[str]] = {index: [] for index in range(len(docs))}
    for name in names:
        where = spec.slices.get(name, {})
        for index, doc in enumerate(docs):
            groups = dict(doc.groups)
            if all(groups.get(column) == value for column, value in where.items()):
                membership[index].append(name)
    return membership


def _accumulate(out: SliceScore, locator, doc, pred: list[tuple[str, int, int]], dropped: int) -> None:
    out.dropped += dropped
    out.docs += 1
    out.gold += len(doc.spans)
    out.pred += len(pred)
    tp, fp, fn, miss, wrong_type, shift, extra = _confusion(doc.spans, pred)
    out.tp += tp
    out.fp += fp
    out.fn += fn
    out.miss += miss
    out.wrong_type += wrong_type
    out.shift += shift
    out.extra += extra
    high = {row[0] for row in doc.spans if _class_of(locator, row[0]) in HIGH_SEVERITY}
    if high:
        out.leaks += leakage_count(
            gold=[row for row in doc.spans if row[0] in high],
            predicted=pred,
            high_types=high,
        )
    per_type = out.per_type
    for type_name, row in _per_type_rows(doc.spans, pred).items():
        total = per_type.setdefault(type_name, TypeScore())
        total.tp += row.tp
        total.fp += row.fp
        total.fn += row.fn


def _class_of(locator, type_name: str) -> str:
    info = locator.taxonomy.types.get(type_name)
    return "" if info is None else info.class_name


def _confusion(gold: list[tuple[str, int, int]], pred: list[tuple[str, int, int]]):
    """Exact match first, then classify every leftover gold span.

    A shift is the same type on an overlapping range. A wrong type is any other
    overlap. A miss is no overlap at all. The three are exclusive, so a reader
    can add them to fn and get the same number.
    """

    used_pred: set[int] = set()
    matched_gold: set[int] = set()
    for g_index, gold_row in enumerate(gold):
        for p_index, pred_row in enumerate(pred):
            if p_index in used_pred:
                continue
            if gold_row == pred_row:
                matched_gold.add(g_index)
                used_pred.add(p_index)
                break
    miss = wrong_type = shift = 0
    for g_index, gold_row in enumerate(gold):
        if g_index in matched_gold:
            continue
        overlaps = [
            pred_row
            for p_index, pred_row in enumerate(pred)
            if p_index not in used_pred and _overlap(gold_row, pred_row)
        ]
        if any(row[0] == gold_row[0] for row in overlaps):
            shift += 1
        elif overlaps:
            wrong_type += 1
        else:
            miss += 1
    extra = sum(
        1
        for p_index, pred_row in enumerate(pred)
        if p_index not in used_pred and not any(_overlap(gold_row, pred_row) for gold_row in gold)
    )
    tp = len(matched_gold)
    return tp, len(pred) - tp, len(gold) - tp, miss, wrong_type, shift, extra


def _per_type_rows(gold: list[tuple[str, int, int]], pred: list[tuple[str, int, int]]) -> dict[str, TypeScore]:
    rows: dict[str, TypeScore] = {}
    for name in {row[0] for row in gold} | {row[0] for row in pred}:
        gold_rows = [row for row in gold if row[0] == name]
        pred_rows = [row for row in pred if row[0] == name]
        tp, fp, fn, _miss, _wrong, _shift, _extra = _confusion(gold_rows, pred_rows)
        rows[name] = TypeScore(tp=tp, fp=fp, fn=fn)
    return rows


def _overlap(left: tuple[str, int, int], right: tuple[str, int, int]) -> bool:
    return left[1] < right[2] and right[1] < left[2]


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float, float]:
    precision = 1.0 if tp + fp == 0 else tp / (tp + fp)
    recall = 1.0 if tp + fn == 0 else tp / (tp + fn)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    beta2 = 4.0
    denom = beta2 * precision + recall
    f2 = 0.0 if denom == 0 else (1 + beta2) * precision * recall / denom
    return precision, recall, f1, f2


def _type_dict(row: TypeScore) -> dict:
    return {
        "tp": row.tp,
        "fp": row.fp,
        "fn": row.fn,
        "precision": row.precision,
        "recall": row.recall,
        "f1": row.f1,
        "f2": row.f2,
    }


def _environment(locator) -> dict:
    import sys

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable": sys.executable,
        "detectors": [type(detector).__name__ for detector in locator.detectors],
    }
