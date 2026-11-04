"""Scoring. Exact-span F1, the pinned public corpora, and the run report.

`score` holds the metric. `corpora` holds the pins and the label fold. `runner`
holds the per-document pass. `cli` is the entry point:

    python -m edgepii.eval.cli --preset rules --corpus nemotron-pii
"""

from edgepii.eval.corpora import (
    CorpusError,
    CorpusSpec,
    GoldDiagnostics,
    corpus_keys,
    load_spec,
)
from edgepii.eval.runner import RunReport, SliceScore, score_corpus, score_docs
from edgepii.eval.score import ScoreReport, exact_span_f1, leakage_count

__all__ = [
    "CorpusError",
    "CorpusSpec",
    "GoldDiagnostics",
    "RunReport",
    "ScoreReport",
    "SliceScore",
    "corpus_keys",
    "exact_span_f1",
    "leakage_count",
    "load_spec",
    "score_corpus",
    "score_docs",
]
