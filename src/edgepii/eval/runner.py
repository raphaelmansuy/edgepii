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
import hashlib
import json
import math
from importlib.metadata import PackageNotFoundError, version
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
SPY_PROTOCOL = "government-id-v2"

from edgepii.eval.score import TypeScore, leakage_count
from edgepii.eval.coverage import character_counts, covered, union_ranges

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
    unmapped: int = 0
    per_type: dict[str, TypeScore] = field(default_factory=dict)
    gold_characters: int = 0
    masked_characters: int = 0
    covered_characters: int = 0
    fully_contained: int = 0
    high_severity_gold: int = 0
    high_severity_documents: int = 0
    leaking_documents: int = 0
    zero_gold_documents: int = 0
    zero_gold_masked_documents: int = 0
    repeated_identifiers: int = 0
    fully_contained_repeated: int = 0
    source_characters: int = 0
    zero_gold_characters: int = 0
    zero_gold_masked_characters: int = 0
    candidate_documents: int = 0
    candidate_gold: int = 0
    candidate_fully_contained: int = 0
    candidate_high_severity_leaks: int = 0
    protection_docs: int = 0
    protection_gold: int = 0
    protection_gold_chars: int = 0
    protection_masked_chars: int = 0
    protection_covered_chars: int = 0
    protection_contained: int = 0
    protection_leaks: int = 0
    protection_leaking_documents: int = 0
    protection_irreversible_chars: int = 0

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
            "high_severity_documents": self.high_severity_documents,
            "high_severity_leaking_documents": self.leaking_documents,
            "dropped_offsets": self.dropped,
            "unmapped_predictions": self.unmapped,
            "protection_plan": {
                "documents": self.protection_docs,
                "gold_spans": self.protection_gold,
                "fully_contained_gold_spans": self.protection_contained,
                "span_recall": self.protection_contained / self.protection_gold if self.protection_gold else None,
                "high_severity_leaks": self.protection_leaks if self.protection_docs else None,
                "high_severity_leaking_documents": self.protection_leaking_documents if self.protection_docs else None,
                "gold_characters": self.protection_gold_chars,
                "masked_characters": self.protection_masked_chars,
                "covered_characters": self.protection_covered_chars,
                "character_recall": self.protection_covered_chars / self.protection_gold_chars if self.protection_gold_chars else None,
                "masking_precision": self.protection_covered_chars / self.protection_masked_chars if self.protection_masked_chars else None,
                "irreversible_characters": self.protection_irreversible_chars,
                "scope": "opt-in eligible candidate union; secret-tainted components irreversible; unavailable for native-label experiments",
            },
            "pre_policy_candidates": {
                "documents": self.candidate_documents,
                "gold_spans": self.candidate_gold,
                "fully_contained_gold_spans": self.candidate_fully_contained,
                "high_severity_leaks": self.candidate_high_severity_leaks,
                "span_recall": self.candidate_fully_contained / self.candidate_gold if self.candidate_gold else None,
                "scope": "mapped requested-type candidates before overlap and score policy; null when unavailable",
            },
            "containment": {
                "source_characters": self.source_characters,
                "gold_characters": self.gold_characters,
                "masked_characters": self.masked_characters,
                "covered_characters": self.covered_characters,
                "character_recall": self.covered_characters / self.gold_characters if self.gold_characters else None,
                "masking_precision": self.covered_characters / self.masked_characters if self.masked_characters else None,
                "masked_character_fraction": self.masked_characters / self.source_characters if self.source_characters else None,
                "fully_contained_gold_spans": self.fully_contained,
                "span_recall": self.fully_contained / self.gold if self.gold else None,
                "high_severity_gold_spans": self.high_severity_gold,
                "zero_gold_documents": self.zero_gold_documents,
                "zero_gold_masked_documents": self.zero_gold_masked_documents,
                "zero_gold_document_mask_rate": self.zero_gold_masked_documents / self.zero_gold_documents if self.zero_gold_documents else None,
                "zero_gold_characters": self.zero_gold_characters,
                "zero_gold_masked_characters": self.zero_gold_masked_characters,
                "zero_gold_masked_character_fraction": self.zero_gold_masked_characters / self.zero_gold_characters if self.zero_gold_characters else None,
                "repeated_identifiers": self.repeated_identifiers,
                "fully_contained_repeated_identifiers": self.fully_contained_repeated,
                "scope": "declared gold policy; zero gold does not establish PII-free text",
            },
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
    evaluation: dict = field(default_factory=dict)
    latency: dict = field(default_factory=dict)

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
            "evaluation": self.evaluation,
            "latency_ms": self.latency,
            "slices": {name: row.to_dict() for name, row in sorted(self.slices.items())},
        }


def score_corpus(
    locator,
    corpus: str,
    cache_dir: Path,
    limit: int | None = None,
    slices: list[str] | None = None,
    types: list[str] | None = None,
    min_score: float | None = None,
) -> RunReport:
    """Score one corpus. `limit` is a prefix per slice, not per corpus.

    A per-slice prefix matters because a corpus can hold its locales in blocks.
    A corpus-wide prefix of 500 would read only the `us` block of Nemotron-PII
    and report an empty `intl` slice.
    """

    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if min_score is not None and not (math.isfinite(min_score) and 0 <= min_score <= 1):
        raise ValueError("min_score must be between zero and one")
    spec = load_spec(corpus)
    known = set(locator.taxonomy.types)
    problems = label_audit(spec, known)
    if problems:
        raise RuntimeError(f"label map for {corpus} is not valid: {problems}")
    requested = list(types) if types is not None else locator.taxonomy.default_types()
    if not requested:
        raise ValueError("evaluation requires at least one type")
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
        records = materialize_spy(records, seed=SPY_SEED, protocol=SPY_PROTOCOL)
    docs, diagnostics = build_docs(records, spec, allowed)

    # One pass over the documents. Each document feeds every slice it belongs to,
    # so a run with four slices does not call the locator four times per document.
    report_slices: dict[str, SliceScore] = {name: SliceScore(name=name) for name in names}
    membership = _slice_membership(spec, names, docs)
    selected = _selected_docs(membership, limit)
    selection_hash = hashlib.sha256()
    durations: list[float] = []
    started = time.perf_counter()
    for index, doc in enumerate(docs):
        if index not in selected:
            continue
        # Hash the actual selected inputs and gold, including slice membership.
        # The digest proves two model runs used the same examples without
        # copying source text or document identifiers into their reports.
        selection_hash.update(json.dumps(
            [index, doc.doc_id, doc.text, doc.spans, sorted(selected[index])],
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8"))
        tick = time.perf_counter()
        result = locator.locate(doc.text, types=sorted(allowed), min_score=min_score)
        durations.append((time.perf_counter() - tick) * 1000)
        pred = [(span.type, span.start, span.end) for span in result.spans]
        protected = _protection_outcome(locator, doc, result, sorted(allowed), min_score)
        for name in selected[index]:
            _accumulate(report_slices[name], locator, doc, pred, result.dropped, getattr(result, "unmapped", 0), getattr(result, "_candidate_ranges", None), protected)
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
        evaluation={
            "types": sorted(allowed),
            "min_score": min_score,
            "fold": "confusables",
            "selection": "prefix_per_slice",
            "selection_sha256": selection_hash.hexdigest(),
            "unique_documents": len(selected),
            "spy_seed": SPY_SEED if spec.spans_encoding == "bio" else None,
            "materialization_protocol": SPY_PROTOCOL if spec.spans_encoding == "bio" else "source-v1",
            "annotation_policy": "author-associated; synthetic US ID shapes" if spec.spans_encoding == "bio" else "source corpus policy",
        },
        latency=_latency_summary(durations),
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
        protected = _protection_outcome(locator, doc, result, ordered, min_score)
        _accumulate(out, locator, doc, pred, result.dropped, getattr(result, "unmapped", 0), getattr(result, "_candidate_ranges", None), protected)
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


def _protection_outcome(locator, doc, result, allowed, min_score):
    candidates = getattr(result, "_candidates", None)
    if candidates is None:
        return None
    from edgepii import protection_plan, redact_protected, restore
    plan = protection_plan(doc.text, candidates, taxonomy=locator.taxonomy, types=allowed,
        min_score=min_score, dropped=result.dropped, unmapped=getattr(result,"unmapped",0), strict=False)
    masked, vault = redact_protected(doc.text, plan)
    if not any(s.irreversible for s in plan.segments):
        assert restore(masked, vault).text == doc.text, "protection round trip failed"
    for a,b in plan._secret_ranges:
        assert not any(doc.text[a:b] in value for value in vault.values()), "secret entered protection vault"
    return ([("",s.start,s.end) for s in plan.segments],
            sum(s.end-s.start for s in plan.segments if s.irreversible))


def _accumulate(out: SliceScore, locator, doc, pred: list[tuple[str, int, int]], dropped: int, unmapped: int = 0, candidates=None, protection=None) -> None:
    out.dropped += dropped
    out.unmapped += unmapped
    out.docs += 1
    out.source_characters += len(doc.text)
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
    if protection is not None:
        protected, irreversible_chars = protection
        protection_masks = union_ranges((row[1], row[2]) for row in protected)
        gc, mc, cc = character_counts(doc.spans, protected)
        out.protection_docs += 1
        out.protection_gold += len(doc.spans)
        out.protection_gold_chars += gc
        out.protection_masked_chars += mc
        out.protection_covered_chars += cc
        out.protection_contained += sum(covered(row[1], row[2], protection_masks) for row in doc.spans)
        out.protection_irreversible_chars += irreversible_chars
        protection_leaks=leakage_count(gold=[r for r in doc.spans if r[0] in high], predicted=protected, high_types=high)
        out.protection_leaks += protection_leaks
        out.protection_leaking_documents += bool(protection_leaks)
    if candidates is not None:
        candidate_masks = union_ranges((row[1], row[2]) for row in candidates)
        out.candidate_documents += 1
        out.candidate_gold += len(doc.spans)
        out.candidate_fully_contained += sum(covered(row[1], row[2], candidate_masks) for row in doc.spans)
        out.candidate_high_severity_leaks += leakage_count(
            gold=[row for row in doc.spans if row[0] in high], predicted=candidates, high_types=high)
    masks = union_ranges((row[1], row[2]) for row in pred)
    gold_chars, masked_chars, covered_chars = character_counts(doc.spans, pred)
    out.gold_characters += gold_chars
    out.masked_characters += masked_chars
    out.covered_characters += covered_chars
    out.fully_contained += sum(covered(row[1], row[2], masks) for row in doc.spans)
    out.high_severity_gold += sum(row[0] in high for row in doc.spans)
    if not doc.spans:
        out.zero_gold_documents += 1
        out.zero_gold_masked_documents += bool(pred)
        out.zero_gold_characters += len(doc.text)
        out.zero_gold_masked_characters += masked_chars
    repeated = {}
    for kind, start, end in doc.spans:
        repeated.setdefault((kind, doc.text[start:end]), []).append((start, end))
    for ranges in repeated.values():
        if len(ranges) > 1:
            out.repeated_identifiers += 1
            out.fully_contained_repeated += all(covered(a, b, masks) for a, b in ranges)
    if high:
        out.high_severity_documents += 1
        leaks = leakage_count(
            gold=[row for row in doc.spans if row[0] in high],
            predicted=pred,
            high_types=high,
        )
        out.leaks += leaks
        out.leaking_documents += bool(leaks)
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

    packages = {}
    for name in ("edgepii", "torch", "transformers", "gliner2", "gliner", "tokenizers",
                 "huggingface-hub", "phonenumbers", "pyyaml", "pyarrow", "faker", "peft"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            pass
    source_hash = hashlib.sha256()
    package = Path(__file__).resolve().parents[1]
    for path in sorted(package.rglob("*")):
        if path.suffix in {".py", ".yaml"}:
            source_hash.update(path.relative_to(package).as_posix().encode())
            source_hash.update(b"\0")
            source_hash.update(path.read_bytes())
            source_hash.update(b"\0")
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable": sys.executable,
        "detectors": [type(detector).__name__ for detector in locator.detectors],
        "devices": [getattr(detector, "device", "cpu") for detector in locator.detectors],
        "packages": packages,
        "source_sha256": source_hash.hexdigest(),
    }


def _latency_summary(durations: list[float]) -> dict:
    """Nearest-rank percentiles of locate calls; excludes loading and scoring."""

    if not durations:
        return {"calls": 0}
    ordered = sorted(durations)
    return {
        "calls": len(ordered),
        "mean": sum(ordered) / len(ordered),
        "p50": ordered[math.ceil(len(ordered) * 0.50) - 1],
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
        "max": ordered[-1],
        "scope": "locate only; excludes model loading and scoring",
    }
