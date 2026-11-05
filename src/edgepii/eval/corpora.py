"""Public PII corpora: pinned bytes, a label map, and gold rows.

A corpus is data, not code. `corpora.yaml` holds the revision, the sha256, the
license, and the fold from each external gold label into taxonomy 2026.11. This
module is the only reader of that file.

Two rules keep a score honest:

1. The bytes are pinned. A download that does not match the sha256 is a failure,
   not a warning, because a moved file makes an old score unreadable.
2. A gold label that the map does not name is reported, never guessed. A silent
   fold would inflate recall.
"""

from __future__ import annotations

import ast
import hashlib
import json
import random
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

import yaml

REGISTRY_VERSION = "1"
_DOWNLOAD = "https://huggingface.co/datasets/{repo}/resolve/{revision}/{file}"


class CorpusError(RuntimeError):
    """A corpus file is absent, truncated, or not the pinned bytes."""


@dataclass(frozen=True, slots=True)
class Drop:
    labels: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class CorpusSpec:
    key: str
    title: str
    role: str
    repo_id: str
    revision: str
    file: str
    sha256: str
    license: str
    license_url: str
    citation: str
    text_column: str
    spans_column: str
    spans_encoding: str
    id_column: str | None
    group_columns: tuple[str, ...]
    slices: dict[str, dict[str, str]]
    labels: dict[str, str]
    drops: tuple[Drop, ...]
    bytes: int | None = None


@dataclass(slots=True)
class GoldDiagnostics:
    """What the map did to the corpus. Every label lands in exactly one bucket."""

    rows: int = 0
    in_scope: int = 0
    out_of_scope: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    unknown: dict[str, int] = field(default_factory=dict)
    text_mismatch: int = 0
    bad_offset: int = 0
    overlapping_rows: int = 0

    def to_dict(self) -> dict:
        return {
            "rows": self.rows,
            "gold_in_scope": self.in_scope,
            "gold_out_of_scope": self.out_of_scope,
            "dropped_labels": dict(sorted(self.dropped.items())),
            "unknown_labels": dict(sorted(self.unknown.items())),
            "gold_text_mismatch": self.text_mismatch,
            "gold_bad_offset": self.bad_offset,
            "rows_with_overlapping_gold": self.overlapping_rows,
        }


@dataclass(frozen=True, slots=True)
class Doc:
    doc_id: str
    text: str
    groups: tuple[tuple[str, str], ...]
    spans: tuple[tuple[str, int, int], ...]


def _registry_path() -> Path:
    return Path(str(files("edgepii").joinpath("eval/corpora.yaml")))


@lru_cache(maxsize=1)
def _registry() -> dict:
    data = yaml.safe_load(_registry_path().read_text(encoding="utf-8"))
    if str(data.get("version")) != REGISTRY_VERSION:
        raise CorpusError(f"registry version {data.get('version')} is not {REGISTRY_VERSION}")
    return data


def corpus_keys() -> list[str]:
    return sorted(_registry()["corpora"])


def load_spec(key: str) -> CorpusSpec:
    rows = _registry()["corpora"]
    if key not in rows:
        raise CorpusError(f"unknown corpus {key}. known: {', '.join(sorted(rows))}")
    row = rows[key]
    drops = tuple(
        Drop(tuple(item["labels"]), str(item["reason"])) for item in row.get("drop", [])
    )
    spec = CorpusSpec(
        key=key,
        title=str(row["title"]),
        role=str(row["role"]),
        repo_id=str(row["repo_id"]),
        revision=str(row["revision"]),
        file=str(row["file"]),
        sha256=str(row["sha256"]),
        license=str(row["license"]),
        license_url=str(row["license_url"]),
        citation=str(row["citation"]),
        text_column=str(row["text_column"]),
        spans_column=str(row["spans_column"]),
        spans_encoding=str(row["spans_encoding"]),
        id_column=None if row.get("id_column") is None else str(row["id_column"]),
        group_columns=tuple(row.get("group_columns") or ()),
        slices={name: dict(where) for name, where in (row.get("slices") or {}).items()},
        labels={str(label): str(public) for label, public in row["labels"].items()},
        drops=drops,
        bytes=None if row.get("bytes") is None else int(row["bytes"]),
    )
    overlap = set(spec.labels) & {label for drop in spec.drops for label in drop.labels}
    if overlap:
        raise CorpusError(f"{key} maps and drops the same label: {', '.join(sorted(overlap))}")
    return spec


def label_audit(spec: CorpusSpec, known_types: set[str]) -> dict[str, list[str]]:
    """Return the map problems. The test suite asserts this dict is empty."""

    problems: dict[str, list[str]] = {}
    bad_types = sorted({public for public in spec.labels.values() if public not in known_types})
    if bad_types:
        problems["public_type_not_in_taxonomy"] = bad_types
    missing_reason = sorted(
        label for drop in spec.drops if not drop.reason.strip() for label in drop.labels
    )
    if missing_reason:
        problems["drop_without_reason"] = missing_reason
    return problems


def download_url(spec: CorpusSpec) -> str:
    return _DOWNLOAD.format(repo=spec.repo_id, revision=spec.revision, file=spec.file)


def ensure_file(spec: CorpusSpec, cache_dir: Path, timeout: float = 120.0) -> Path:
    """Return a local path whose bytes match the pin. Download once."""

    local = cache_dir / spec.key / Path(spec.file).name
    if local.is_file() and _hash_matches(local, spec):
        return local
    local.parent.mkdir(parents=True, exist_ok=True)
    partial = local.with_suffix(local.suffix + ".part")
    url = download_url(spec)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response, partial.open("wb") as out:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise CorpusError(f"download failed for {spec.key}: {exc}") from exc
    if not _hash_matches(partial, spec):
        partial.unlink(missing_ok=True)
        raise CorpusError(
            f"sha256 mismatch for {spec.key}: {spec.repo_id}@{spec.revision} {spec.file}"
        )
    partial.replace(local)
    return local


def _hash_matches(path: Path, spec: CorpusSpec) -> bool:
    size = path.stat().st_size
    if spec.bytes is not None and size != spec.bytes:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest() == spec.sha256


def read_raw(path: Path) -> list[dict]:
    """Read a pinned corpus file into plain records."""

    if path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise CorpusError('parquet needs the eval extra: pip install -e ".[eval]"') from exc
        return pq.read_table(path).to_pylist()
    if path.suffix == ".jsonl":
        records = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
    raise CorpusError(f"unsupported file type {path.suffix}")


def parse_spans(raw, encoding: str) -> list[dict]:
    if encoding not in {"json", "python_literal", "bio"}:
        raise CorpusError(f"unknown spans encoding {encoding}")
    if raw is None:
        return []
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        raise CorpusError(f"spans column holds {type(raw).__name__}")
    text = raw.strip()
    if text == "" or text == "[]":
        return []
    if encoding == "json":
        return json.loads(text)
    return ast.literal_eval(text)


def bio_to_spans(record: dict, text: str) -> list[dict]:
    """Turn a BIO-tagged record into character spans on `text`.

    The corpus stores tokens, a tag per token, and a flag that says whether the
    token carries a trailing space. The offsets are rebuilt by walking the text,
    then checked against it. A token whose slice does not match the text is
    shifted by a whitespace fix or dropped, never guessed.

    A tag is `B-TYPE`, `I-TYPE`, or `O`. An `I-` tag continues the previous span
    only when the type matches and the two tokens touch.
    """

    tokens = record.get("tokens") or []
    tags = record.get("ent_tags") or []
    if len(tokens) != len(tags):
        return []

    spans: list[dict] = []
    cursor = 0
    open_type: str | None = None
    open_start = 0
    open_end = 0

    def close() -> None:
        nonlocal open_type
        if open_type is not None:
            # Tokens carry their trailing space, so trim the entity edges. The
            # locator trims the same way, and exact-span F1 compares the two.
            start, end = open_start, open_end
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            if start < end:
                spans.append({"label": open_type, "start": start, "end": end})
            open_type = None

    for token, tag in zip(tokens, tags, strict=False):
        piece = str(token)
        prefix, _, label = str(tag).partition("-")

        start = text.find(piece, cursor)
        if start < 0:
            close()
            continue
        end = start + len(piece)
        cursor = end

        if prefix == "B" or (prefix == "I" and open_type != label):
            close()
            open_type, open_start, open_end = label, start, end
        elif prefix == "I" and open_type == label:
            # Only extend when the two tokens are adjacent on the source string.
            if start == open_end:
                open_end = end
            else:
                close()
                open_type, open_start, open_end = label, start, end
        else:
            close()

    close()
    return spans


def build_docs(
    records: list[dict],
    spec: CorpusSpec,
    allowed_types: set[str],
    slice_name: str | None = None,
    limit: int | None = None,
) -> tuple[list[Doc], GoldDiagnostics]:
    """Fold raw records into gold documents. A slice filters, then the limit cuts.

    The limit takes a prefix, not a random sample, so two runs read the same
    rows. A random sample would make a report unreadable next to an older one.
    """

    where = spec.slices.get(slice_name or "", {})
    if slice_name is not None and not where:
        raise CorpusError(f"corpus {spec.key} has no slice {slice_name}")
    diagnostics = GoldDiagnostics()
    docs: list[Doc] = []
    for raw in records:
        if not _in_slice(raw, where):
            continue
        if limit is not None and len(docs) >= limit:
            break
        doc = _to_doc(raw, spec, allowed_types, diagnostics)
        docs.append(doc)
    return docs, diagnostics


def _in_slice(raw: dict, where: dict[str, str]) -> bool:
    return all(str(raw.get(column)) == str(value) for column, value in where.items())


def record_text(raw: dict, spec: CorpusSpec) -> str:
    """Return the document text. A BIO corpus stores tokens, not a text column."""

    text = raw.get(spec.text_column)
    if isinstance(text, str):
        return text
    tokens = raw.get("tokens")
    if isinstance(tokens, list):
        return "".join(str(token) for token in tokens)
    raise CorpusError(f"corpus {spec.key} row has no text in {spec.text_column}")


def materialize_spy(records: list[dict], seed: int, protocol: str = "government-id-v2") -> list[dict]:
    """Replace SPY's placeholders with seeded fake values.

    SPY ships templates such as `<NAME>` rather than real strings, so a score
    needs a materialisation step. government-id-v2 uses local seeded generators
    and government-ID-shaped ID_NUM values. legacy-v1 retains the previous
    first-generator behavior. Different protocols are different evaluations.

    A materialised corpus is derived data, not the pinned bytes. The pin still
    covers the template file, and the seed is recorded in the report.
    """

    try:
        from faker import Faker
    except ImportError as exc:
        raise CorpusError(
            'SPY needs faker to fill its templates: pip install "edgepii[eval]"'
        ) from exc

    if protocol not in {"government-id-v2", "legacy-v1"}:
        raise CorpusError("unknown SPY materialization protocol")
    fake = Faker()
    fake.seed_instance(seed)
    choices = random.Random(seed)

    generators = {
        "EMAIL": [fake.ascii_email, fake.ascii_free_email],
        "NAME": [fake.name],
        "URL": [lambda: fake.uri(deep=1), lambda: fake.uri(deep=2)],
        "PHONE_NUM": [fake.phone_number],
        "ID_NUM": [
            fake.ripe_id,
            fake.msisdn,
            fake.ssn,
            fake.sbn9,
            fake.iban,
            fake.credit_card_number,
        ],
        "ADDRESS": [fake.street_address],
        "USERNAME": [fake.user_name],
    }
    if protocol == "government-id-v2":
        # Our public GOV_ID mapping requires a government identifier, not a
        # RIPE organization handle or a financial account. This derived track
        # uses synthetic US SSN-shaped identifiers, not a locale-validity claim.
        generators["ID_NUM"] = [fake.ssn]

    out: list[dict] = []
    for record in records:
        tokens = list(record.get("tokens") or [])
        tags = list(record.get("ent_tags") or [])
        spaces = list(record.get("trailing_whitespaces") or [True] * len(tokens))
        if len(tokens) != len(tags):
            out.append(record)
            continue

        new_tokens: list[str] = []
        new_tags: list[str] = []
        new_spaces: list[bool] = []
        for token, tag, space in zip(tokens, tags, spaces, strict=False):
            if not str(tag).startswith("B-"):
                new_tokens.append(str(token))
                new_tags.append(str(tag))
                new_spaces.append(bool(space))
                continue

            entity = str(tag)[2:]
            pool = generators.get(entity)
            if not pool:
                new_tokens.append(str(token))
                new_tags.append(str(tag))
                new_spaces.append(bool(space))
                continue

            generator = pool[0] if protocol == "legacy-v1" else choices.choice(pool)
            words = str(generator()).split()
            if not words:
                words = ["x"]
            for index, word in enumerate(words):
                last = index == len(words) - 1
                # The source tokens carry their own trailing space, so a token
                # that ends a word must do the same. Joining bare words would
                # fuse an entity into the next one.
                if not last:
                    new_tokens.append(f"{word} ")
                elif space:
                    new_tokens.append(f"{word} ")
                else:
                    new_tokens.append(word)
                new_tags.append(f"B-{entity}" if index == 0 else f"I-{entity}")
                new_spaces.append(True if not last else bool(space))

        out.append(
            {
                **record,
                "tokens": new_tokens,
                "ent_tags": new_tags,
                "trailing_whitespaces": new_spaces,
            }
        )
    return out


def _to_doc(raw: dict, spec: CorpusSpec, allowed_types: set[str], diagnostics: GoldDiagnostics) -> Doc:
    text = record_text(raw, spec)
    groups = tuple((column, str(raw.get(column))) for column in spec.group_columns)
    doc_id = str(raw[spec.id_column]) if spec.id_column else str(diagnostics.rows)
    spans, overlapping = gold_spans(text, raw, spec, allowed_types, diagnostics)
    diagnostics.rows += 1
    if overlapping:
        diagnostics.overlapping_rows += 1
    return Doc(doc_id=doc_id, text=text, groups=groups, spans=spans)


def gold_spans(
    text: str,
    raw_spans,
    spec: CorpusSpec,
    allowed_types: set[str],
    diagnostics: GoldDiagnostics,
) -> tuple[tuple[tuple[str, int, int], ...], bool]:
    """Return non-overlapping gold triples. An unknown label is counted, not folded."""

    rows: list[tuple[str, int, int]] = []
    if spec.spans_encoding == "bio":
        # A BIO corpus needs the whole record: tokens, tags, and spacing.
        items = bio_to_spans(raw_spans, text)
    else:
        # Other encodings pass the spans column alone.
        column = raw_spans.get(spec.spans_column) if isinstance(raw_spans, dict) else raw_spans
        items = parse_spans(column, spec.spans_encoding)
    for item in items:
        label = str(item.get("label") or "")
        public = spec.labels.get(label)
        if public is None:
            if any(label in drop.labels for drop in spec.drops):
                diagnostics.dropped[label] = diagnostics.dropped.get(label, 0) + 1
            else:
                diagnostics.unknown[label] = diagnostics.unknown.get(label, 0) + 1
            continue
        start, end = int(item["start"]), int(item["end"])
        if not 0 <= start < end <= len(text):
            diagnostics.bad_offset += 1
            continue
        if "text" in item and item["text"] != text[start:end]:
            # The offsets are the label. The text field is a copy that can
            # differ in case. Count it, and keep the offsets.
            diagnostics.text_mismatch += 1
        if public not in allowed_types:
            diagnostics.out_of_scope += 1
            continue
        diagnostics.in_scope += 1
        rows.append((public, start, end))
    # Sort by position, not by type. The overlap trim below walks left to right.
    rows.sort(key=lambda row: (row[1], -row[2], row[0]))
    kept, overlapping = _drop_overlaps(rows)
    return tuple(sorted(kept)), overlapping


def _drop_overlaps(rows: list[tuple[str, int, int]]) -> tuple[list[tuple[str, int, int]], bool]:
    """Keep the longest span of a stack. A corpus row can nest two labels.

    Exact-span scoring compares one range at a time. A nested pair such as a
    company name that holds a person name cannot both be predicted, because the
    locator returns one non-overlapping list. The longer range wins, and the row
    is flagged, because a reader must know the gold was trimmed.
    """

    kept: list[tuple[str, int, int]] = []
    overlapping = False
    for row in rows:
        if kept and row[1] < kept[-1][2]:
            overlapping = True
            outer = kept[-1]
            if row[2] - row[1] > outer[2] - outer[1]:
                kept[-1] = row
            continue
        kept.append(row)
    return kept, overlapping
