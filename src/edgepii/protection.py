"""Opt-in protection of every eligible candidate, independent of typed arbitration."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace

from edgepii.labelmap import Taxonomy, load_taxonomy
from edgepii.span import Span


class IncompleteDetectionError(ValueError):
    """Strict protection rejected detector diagnostics; contains no source values."""


@dataclass(frozen=True, slots=True)
class ProtectionSegment:
    start: int
    end: int
    types: tuple[str, ...]
    detector_ids: tuple[str, ...]
    irreversible: bool

    def to_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "types": list(self.types),
                "irreversible": self.irreversible}


@dataclass(frozen=True, slots=True)
class ProtectionPlan:
    segments: tuple[ProtectionSegment, ...]
    taxonomy_version: str
    source_length: int
    dropped: int = 0
    unmapped: int = 0
    _source_fingerprint: str = field(default="", repr=False)
    _secret_ranges: tuple[tuple[int, int], ...] = field(default=(), repr=False)

    def to_dict(self) -> dict:
        """Offsets, public types, and counts only; excludes text and source hash."""
        return {"taxonomy_version": self.taxonomy_version,
                "source_length": self.source_length, "dropped": self.dropped,
                "unmapped": self.unmapped,
                "segments": [s.to_dict() for s in self.segments]}


def _fingerprint(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8", errors="surrogatepass")).hexdigest()


def protection_plan(source: str, candidates, *, taxonomy: str | Taxonomy = "2026.11",
                    types: list[str] | None = None, min_score: float | None = None,
                    drop_unscored: bool = False, dropped: int = 0, unmapped: int = 0,
                    strict: bool = True, known_secrets: tuple[str, ...] = ()) -> ProtectionPlan:
    """Protect the union of eligible candidates. Does not repair invalid spans.

    An entire directly/transitively overlapping component becomes irreversible
    if any member is a secret. This conservative policy prevents secret fragments
    being vaulted; it may make other values in that component non-restorable.
    Exact repeated known secrets are propagated as policy, never offset repair.
    """
    if not isinstance(source, str):
        raise TypeError(type(source).__name__)
    if min_score is not None and not (math.isfinite(min_score) and 0 <= min_score <= 1):
        raise ValueError("min_score must be between zero and one")
    if dropped < 0 or unmapped < 0:
        raise ValueError("diagnostic counts must be nonnegative")
    if strict and (dropped or unmapped):
        raise IncompleteDetectionError(f"detector diagnostics: dropped={dropped}, unmapped={unmapped}")
    loaded = taxonomy if isinstance(taxonomy, Taxonomy) else load_taxonomy(taxonomy)
    allowed = set(loaded.default_types() if types is None else types)
    for name in allowed:
        loaded.require(name)
    eligible = []
    secrets = set(known_secrets)
    if any(not isinstance(value, str) or not value for value in secrets):
        raise ValueError("known secrets must be non-empty strings")
    for span in candidates:
        if (not isinstance(span, Span) or type(span.start) is not int or type(span.end) is not int
                or not 0 <= span.start < span.end <= len(source)
                or source[span.start:span.end] != span.text):
            raise ValueError("invalid original-source protection candidate")
        if span.type not in loaded.types:
            raise ValueError("unsupported protection candidate type")
        if span.score is not None and not (math.isfinite(span.score) and 0 <= span.score <= 1):
            raise ValueError("invalid candidate score")
        if span.type not in allowed:
            continue
        if min_score is not None and ((span.score is None and drop_unscored)
                                      or (span.score is not None and span.score < min_score)):
            continue
        eligible.append(span)
        if loaded.require(span.type).redact == "irreversible":
            secrets.add(span.text)
    secret_ranges = set()
    # Literal repetition is an explicit protection policy. All input candidate
    # offsets were validated above; this never searches to fix a rejected hit.
    for value in sorted(secrets):
        start = source.find(value)
        while start != -1:
            end = start + len(value)
            secret_ranges.add((start, end))
            eligible.append(Span("SECRET", start, end, source[start:end], None,
                                 "policy.secret_repeat", "secret"))
            start = source.find(value, start + 1)
    segments = _components(ProtectionSegment(s.start, s.end, (s.type,), (s.detector_id,),
        loaded.require(s.type).redact == "irreversible") for s in eligible)
    return ProtectionPlan(segments, loaded.version, len(source), dropped, unmapped,
                          _fingerprint(source), tuple(sorted(secret_ranges)))


def _components(rows) -> tuple[ProtectionSegment, ...]:
    segments = []
    for segment in sorted(rows, key=lambda s: (s.start, s.end, s.types, s.detector_ids)):
        if segments and segment.start < segments[-1].end:
            previous = segments.pop()
            segments.append(ProtectionSegment(previous.start, max(previous.end, segment.end),
                tuple(sorted(set(previous.types) | set(segment.types))),
                tuple(sorted(set(previous.detector_ids) | set(segment.detector_ids))),
                previous.irreversible or segment.irreversible))
        else:
            segments.append(segment)
    return tuple(segments)


def _extend_secrets(source, plan, secrets):
    rows = list(plan.segments)
    ranges = set(plan._secret_ranges)
    for value in secrets:
        start = source.find(value)
        while start != -1:
            end = start + len(value)
            ranges.add((start, end))
            rows.append(ProtectionSegment(start, end, ("SECRET",), ("policy.secret_repeat",), True))
            start = source.find(value, start + 1)
    return replace(plan, segments=_components(rows), _secret_ranges=tuple(sorted(ranges)))


def redact_protected(source: str, plan: ProtectionPlan) -> tuple[str, dict[str, str]]:
    """Mask the plan; reversible components get neutral PROTECTED placeholders."""
    from edgepii.restore import _pattern_for
    if not isinstance(source, str):
        raise TypeError(type(source).__name__)
    if len(source) != plan.source_length or _fingerprint(source) != plan._source_fingerprint:
        raise ValueError("protection plan does not match the source")
    vault = {}
    replacements = []
    index = 0
    previous_end = 0
    seen = {}
    secret_token = "<SECRET>"
    secret_index = 0
    while _pattern_for(secret_token).search(source):
        secret_index += 1
        secret_token = f"<SECRET_{secret_index}>"
    for segment in plan.segments:
        if not previous_end <= segment.start < segment.end <= len(source):
            raise ValueError("invalid protection segment order or bounds")
        previous_end = segment.end
        if segment.irreversible:
            token = secret_token
        else:
            value = source[segment.start:segment.end]
            token = seen.get(value)
            if token is None:
                while True:
                    index += 1
                    token = f"<PROTECTED_{index}>"
                    if not _pattern_for(token).search(source):
                        break
                seen[value] = token
                vault[token] = value
        replacements.append((segment.start, segment.end, token))
    masked = source
    for start, end, token in reversed(replacements):
        masked = masked[:start] + token + masked[end:]
    return masked, vault


def protect_mapping(value, locator, *, types=None, min_score=None, strict=True, field_types=None):
    """Two-pass protection; known secrets are irreversible across string leaves."""
    from edgepii.toolcall import FieldHit, MaskedMapping, _scope
    from edgepii.restore import _pattern_for
    leaves = []
    field_types = {} if field_types is None else dict(field_types)
    if any(not isinstance(path,tuple) for path in field_types):
        raise ValueError("field policy paths must be tuples")
    used = set()
    def collect(node, path="", key_path=()):
        if key_path in field_types and not isinstance(node,str):
            raise ValueError("field policy requires a string leaf")
        if isinstance(node, str):
            if key_path in field_types:
                kind = field_types[key_path]
                locator.taxonomy.require(kind)
                used.add(key_path)
                candidates = [Span(kind,0,len(node),node,None,"policy.field",kind)] if node else []
                plan = protection_plan(node,candidates,taxonomy=locator.taxonomy,types=[kind])
            else:
                plan = locator.plan(node, types=types, min_score=min_score, strict=strict)
            leaves.append((path, node, plan))
        elif isinstance(node, dict):
            for key, item in node.items():
                collect(item, f"{path}.{key}" if path else str(key), key_path+(key,))
        elif isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                collect(item, f"{path}[{i}]", key_path+(i,))
    collect(value)
    if used != set(field_types):
        raise ValueError("field policy path did not match a string leaf")
    secrets = tuple(sorted({source[a:b] for _, source, plan in leaves for a,b in plan._secret_ranges}))
    vault, hits = {}, []
    dropped = sum(plan.dropped for _, _, plan in leaves)
    iterator = iter(leaves)
    def walk(node):
        if isinstance(node, str):
            path, source, plan = next(iterator)
            # Reuse the plan; no second model call. Whole-component secret
            # taint is retained when adding cross-leaf exact secret copies.
            augmented = _extend_secrets(source, plan, secrets)
            masked, local = redact_protected(source, augmented)
            for token, original in local.items():
                index = len(vault)
                scoped = _scope(token, index)
                while any(_pattern_for(scoped).search(text) for _, text, _ in leaves):
                    index += 1
                    scoped = _scope(token, index)
                while scoped in vault:
                    index += 1
                    scoped = _scope(token, index)
                masked = masked.replace(token, scoped)
                vault[scoped] = original
            if augmented.segments:
                hit_types = set(t for s in plan.segments for t in s.types)
                if augmented._secret_ranges:
                    hit_types.add("SECRET")
                hits.append(FieldHit(path, tuple(sorted(hit_types))))
            return masked
        if isinstance(node, dict):
            return {k:walk(v) for k,v in node.items()}
        if isinstance(node, (list, tuple)):
            items = [walk(v) for v in node]
            return items if isinstance(node, list) else tuple(items)
        return node
    return MaskedMapping(walk(value), vault, tuple(hits), dropped,
                         sum(plan.unmapped for _, _, plan in leaves))
