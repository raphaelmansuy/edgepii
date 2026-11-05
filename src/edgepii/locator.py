"""Locator. Model libraries stay inside detector modules."""

from __future__ import annotations

import logging
import os
from dataclasses import replace

from edgepii.check import slice_text
from edgepii.errors import DetectorLoadError
from edgepii.labelmap import Taxonomy, load_taxonomy
from edgepii.merge import merge_spans
from edgepii.presets import PRESETS
from edgepii.protocol import Hit, coerce_hit
from edgepii.span import LocateResult, Span
from edgepii.windows import split_windows
from edgepii import normalize, quasi

log = logging.getLogger("edgepii")


class Locator:
    def __init__(
        self,
        detectors: list,
        taxonomy: Taxonomy,
        preset: str,
        revision: str,
    ) -> None:
        self._detectors = detectors
        self._taxonomy = taxonomy
        self.preset_name = preset
        self.revision = revision

    @property
    def taxonomy(self) -> Taxonomy:
        """The loaded type list. An eval report reads it, and every call uses it."""

        return self._taxonomy

    @property
    def detectors(self) -> tuple:
        """The detector objects in order. Read only, for a report or a test."""

        return tuple(self._detectors)

    @classmethod
    def preset(cls, name: str, device: str = "cpu", taxonomy: str = "2026.11") -> Locator:
        row = PRESETS.get(name)
        if row is None:
            raise DetectorLoadError(f"unknown preset {name}")
        loaded = load_taxonomy(taxonomy)
        detectors = [_build(kind, row.repo_id, row.revision, row.extra, device, loaded) for kind in row.detectors]
        return cls(detectors, loaded, row.name, row.revision)

    @classmethod
    def from_detectors(cls, detectors: list, taxonomy: str = "2026.11") -> Locator:
        return cls(list(detectors), load_taxonomy(taxonomy), "custom", "custom")

    def locate(
        self,
        source: str,
        types: list[str] | None = None,
        taxonomy: str | None = None,
        min_score: float | None = None,
        fold: bool | str = "confusables",
        drop_unscored: bool = False,
    ) -> LocateResult:
        """Return spans on `source`. Offsets always index the caller's string.

        `fold` controls character folding before matching. A look-alike character
        from another script, a fullwidth digit, or a zero-width space otherwise
        hides a value from every detector. Folded spans are mapped back to the
        source, so the slice check still holds and a mask removes the
        obfuscated characters as well.

        `fold=False` turns the step off. `fold="confusables"` is the default and
        drops invisible characters, unfolds compatibility forms, and folds the
        confusable table in `normalize.py`.
        """

        if not isinstance(source, str):
            raise TypeError(type(source).__name__)
        loaded = self._taxonomy if taxonomy is None else load_taxonomy(taxonomy)
        allowed = loaded.default_types() if types is None else list(types)
        for name in allowed:
            loaded.require(name)
        labels = loaded.raw_labels_for(allowed)

        if fold is False:
            scan_source = source
            folded = None
        else:
            folded = normalize.fold(source)
            scan_source = folded.text

        spans: list[Span] = []
        dropped = 0
        unmapped = 0
        for detector in self._detectors:
            schema = getattr(detector, "label_schema", None)
            detector_labels = labels if schema is None else loaded.prompt_labels_for(allowed, schema)
            found, failed, unknown = _run_detector(detector, scan_source, detector_labels, loaded)
            spans.extend(found)
            dropped += failed
            unmapped += unknown
        if folded is not None and folded.changed:
            spans = _map_to_source(source, spans, folded)
        merged = merge_spans(
            spans, loaded, set(allowed), min_score=min_score, drop_unscored=drop_unscored
        )
        _log_spans(merged)
        return LocateResult(
            taxonomy_version=loaded.version,
            spans=tuple(merged),
            dropped=dropped,
            preset=self.preset_name,
            revision=self.revision,
            quasi=quasi.find_combinations(source),
            unmapped=unmapped,
            _candidate_ranges=tuple((s.type, s.start, s.end) for s in spans if s.type in allowed),
        )

    def locate_many(
        self,
        sources: list[str],
        types: list[str] | None = None,
        min_score: float | None = None,
        fold: bool | str = "confusables",
    ) -> list[LocateResult]:
        return [
            self.locate(source, types=types, min_score=min_score, fold=fold)
            for source in sources
        ]


def _map_to_source(source: str, spans: list[Span], folded) -> list[Span]:
    """Move spans from the folded text back onto the source string.

    A span is kept only when the source slice is non-empty. The `text` field is
    the source slice, never the folded text, so a caller can always mask it with
    an offset pair.
    """

    mapped: list[Span] = []
    for span in spans:
        start, end = folded.to_source(span.start, span.end)
        if start < 0 or end <= start or end > len(source):
            continue
        mapped.append(
            Span(
                type=span.type,
                start=start,
                end=end,
                text=source[start:end],
                score=span.score,
                detector_id=span.detector_id,
                raw_label=span.raw_label,
            )
        )
    return mapped


def _build(kind: str, repo_id: str | None, revision: str, extra: str | None, device: str, taxonomy: Taxonomy):
    if kind == "rules":
        from edgepii.detectors.rules import RuleDetector

        return RuleDetector()
    if repo_id is None:
        raise DetectorLoadError(f"extra={extra} repo=none revision={revision}")
    if kind == "hf_token":
        from edgepii.detectors.hf_token import HfTokenDetector

        return HfTokenDetector(repo_id, revision, device)
    if kind == "gliner2":
        from edgepii.detectors.gliner2 import Gliner2Detector

        return Gliner2Detector(repo_id, revision, device)
    if kind == "gliner":
        from edgepii.detectors.gliner import GlinerDetector

        return GlinerDetector(repo_id, revision, device)
    if kind == "uie":
        from edgepii.detectors.uie import UieDetector

        return UieDetector(repo_id, revision, taxonomy.schema_zh, device)
    raise DetectorLoadError(f"extra={extra} repo={repo_id} revision={revision}")


def _run_detector(detector, source: str, labels: list[str], taxonomy: Taxonomy) -> tuple[list[Span], int, int]:
    max_chars = int(getattr(detector, "max_chars", 1_000_000))
    overlap = int(getattr(detector, "overlap_chars", 64))
    spans: list[Span] = []
    dropped = 0
    unmapped = 0
    for start, end in split_windows(source, max_chars, overlap):
        chunk = source[start:end]
        raw_rows = detector.locate(chunk, labels)
        for raw in raw_rows:
            hit = coerce_hit(raw)
            hit = replace(hit, start=hit.start + start, end=hit.end + start)
            text = slice_text(source, hit)
            if text is None:
                dropped += 1
                continue
            text, hit = _trim_edges(source, hit, text)
            if text is None:
                continue
            public = taxonomy.public_type(hit.raw_label)
            if public is None:
                unmapped += 1
                continue
            spans.append(
                Span(
                    type=public,
                    start=hit.start,
                    end=hit.end,
                    text=text,
                    score=hit.score,
                    detector_id=hit.detector_id,
                    raw_label=hit.raw_label,
                )
            )
    return spans, dropped, unmapped


def _trim_edges(source: str, hit: Hit, text: str) -> tuple[str | None, Hit]:
    """Drop tokenizer spaces that sit on the edge of a character span."""

    stripped = text.strip()
    if stripped == "":
        return None, hit
    if stripped == text:
        return text, hit
    leading = len(text) - len(text.lstrip())
    trailing = len(text) - len(text.rstrip())
    start = hit.start + leading
    end = hit.end - trailing
    if source[start:end] != stripped:
        return None, hit
    return stripped, replace(hit, start=start, end=end)


def _log_spans(spans: list[Span]) -> None:
    show_text = os.environ.get("EDGEPII_LOG_TEXT") == "1"
    for span in spans:
        log.info(
            "span detector_id=%s type=%s start=%s end=%s score=%s",
            span.detector_id,
            span.type,
            span.start,
            span.end,
            span.score,
        )
        if show_text:
            log.debug("span text=%s", span.text)
