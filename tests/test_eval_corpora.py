"""The public corpus pin, the label map, and the per-document score.

No network. Every test builds its own records, so the suite runs offline and a
corpus pin change cannot hide behind a download.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from edgepii import Locator
from edgepii.eval import corpora
from edgepii.eval.corpora import (
    CorpusError,
    GoldDiagnostics,
    build_docs,
    corpus_keys,
    download_url,
    gold_spans,
    label_audit,
    load_spec,
    parse_spans,
)
from edgepii.eval.runner import score_docs
from edgepii.labelmap import load_taxonomy


def test_registry_is_a_pin_not_a_moving_file():
    """Every corpus names a revision, a sha256, and a license."""

    # A new corpus is a deliberate edit to this list, never a silent addition.
    assert corpus_keys() == [
        "gretel-finance-en",
        "nemotron-pii",
        "spy-legal",
        "spy-medical",
    ]
    for key in corpus_keys():
        spec = load_spec(key)
        assert len(spec.revision) == 40, key
        assert len(spec.sha256) == 64, key
        assert spec.license, key
        assert spec.license_url.startswith("https://"), key
        assert spec.citation.startswith("https://"), key
        assert "resolve/" in download_url(spec), key
        assert spec.revision in download_url(spec), key


def test_external_licenses_allow_redistribution():
    """A corpus whose license forbids redistribution cannot be a public gate."""

    allowed = {"CC-BY-4.0", "Apache-2.0", "MIT", "CC0-1.0"}
    for key in corpus_keys():
        assert load_spec(key).license in allowed, key


def test_label_map_names_only_taxonomy_types():
    """A fold into a type outside 2026.11 would fail at call time, not at build time."""

    known = set(load_taxonomy().types)
    for key in corpus_keys():
        spec = load_spec(key)
        assert label_audit(spec, known) == {}, key


def test_every_drop_names_a_reason():
    """A label with no map needs a written reason, not a silent skip."""

    for key in corpus_keys():
        spec = load_spec(key)
        for drop in spec.drops:
            assert drop.reason.strip(), (key, drop.labels)
            assert len(drop.reason) > 40, (key, drop.labels)


def test_a_label_is_never_mapped_and_dropped():
    for key in corpus_keys():
        spec = load_spec(key)
        mapped = set(spec.labels)
        dropped = {label for drop in spec.drops for label in drop.labels}
        assert mapped & dropped == set(), key


def test_unknown_label_is_counted_not_guessed():
    """A new gold label must appear in the report, not fold into a neighbour."""

    spec = load_spec("nemotron-pii")
    diagnostics = GoldDiagnostics()
    spans = [{"start": 0, "end": 4, "label": "iris_scan", "text": "Ada!"}]
    rows, _ = gold_spans("Ada! lives at 12 Main.", spans, spec, {"PERSON"}, diagnostics)
    assert rows == ()
    assert diagnostics.unknown == {"iris_scan": 1}
    assert diagnostics.in_scope == 0


def test_a_dropped_label_is_counted_separately_from_an_unknown_one():
    spec = load_spec("nemotron-pii")
    diagnostics = GoldDiagnostics()
    spans = [{"start": 0, "end": 4, "label": "blood_type", "text": "Ada!"}]
    gold_spans("Ada! lives at 12 Main.", spans, spec, {"PERSON"}, diagnostics)
    assert diagnostics.dropped == {"blood_type": 1}
    assert diagnostics.unknown == {}


def test_a_type_outside_the_call_subset_is_out_of_scope():
    """The run reports what it did not ask for, so a narrow run stays readable."""

    spec = load_spec("nemotron-pii")
    diagnostics = GoldDiagnostics()
    spans = [{"start": 0, "end": 3, "label": "first_name", "text": "Ada"}]
    rows, _ = gold_spans("Ada lives at 12 Main.", spans, spec, {"EMAIL"}, diagnostics)
    assert rows == ()
    assert diagnostics.out_of_scope == 1


def test_nested_gold_keeps_the_longer_span():
    """One non-overlapping list is the contract, so gold must be one list too."""

    spec = load_spec("gretel-finance-en")
    diagnostics = GoldDiagnostics()
    text = "The Martin Group hired Ada."
    spans = [
        {"start": 0, "end": 16, "label": "company"},
        {"start": 4, "end": 10, "label": "last_name"},
    ]
    rows, overlapping = gold_spans(text, spans, spec, {"ORG", "PERSON"}, diagnostics)
    assert overlapping is True
    assert rows == (("ORG", 0, 16),)


def test_gold_offsets_that_exceed_the_text_are_counted():
    spec = load_spec("nemotron-pii")
    diagnostics = GoldDiagnostics()
    spans = [{"start": 0, "end": 99, "label": "first_name"}]
    rows, _ = gold_spans("Ada", spans, spec, {"PERSON"}, diagnostics)
    assert rows == ()
    assert diagnostics.bad_offset == 1


def test_text_copy_mismatch_is_counted_and_the_offset_is_kept():
    """A case difference in the copy must not move the span."""

    spec = load_spec("nemotron-pii")
    diagnostics = GoldDiagnostics()
    spans = [{"start": 0, "end": 3, "label": "first_name", "text": "ADA"}]
    rows, _ = gold_spans("Ada lives at 12 Main.", spans, spec, {"PERSON"}, diagnostics)
    assert rows == (("PERSON", 0, 3),)
    assert diagnostics.text_mismatch == 1


def test_parquet_encoding_is_declared_per_corpus():
    assert load_spec("nemotron-pii").spans_encoding == "python_literal"
    assert load_spec("gretel-finance-en").spans_encoding == "json"
    assert parse_spans("[{'start': 0, 'end': 3, 'label': 'name'}]", "python_literal") == [
        {"start": 0, "end": 3, "label": "name"}
    ]
    assert parse_spans('[{"start": 0, "end": 3, "label": "name"}]', "json") == [
        {"start": 0, "end": 3, "label": "name"}
    ]
    assert parse_spans("", "json") == []
    with pytest.raises(CorpusError):
        parse_spans("[]", "xml")


def test_a_bad_sha256_is_an_error_not_a_warning(tmp_path):
    """A moved file would make an old score unreadable, so the run must stop."""

    spec = load_spec("nemotron-pii")
    stale = replace(spec, sha256="0" * 64)
    path = tmp_path / "corpus.bin"
    path.write_bytes(b"not the pinned bytes")
    assert corpora._hash_matches(path, stale) is False
    assert corpora._hash_matches(path, spec) is False


def test_build_docs_reads_the_pinned_columns():
    spec = load_spec("nemotron-pii")
    records = [
        {
            "uid": "u1",
            "locale": "us",
            "document_format": "structured",
            "domain": "Life",
            "text": "Ada wrote to ada@example.com.",
            "spans": "[{'start': 13, 'end': 28, 'label': 'email', 'text': 'ada@example.com'}]",
        }
    ]
    docs, diagnostics = build_docs(records, spec, set(spec.labels.values()))
    assert len(docs) == 1
    assert docs[0].doc_id == "u1"
    assert dict(docs[0].groups)["locale"] == "us"
    assert docs[0].spans == (("EMAIL", 13, 28),)
    assert diagnostics.in_scope == 1


def test_a_missing_slice_name_is_an_error():
    spec = load_spec("nemotron-pii")
    with pytest.raises(CorpusError):
        build_docs([], spec, {"EMAIL"}, slice_name="klingon")


def test_the_limit_takes_a_prefix_so_two_runs_read_the_same_rows():
    spec = load_spec("nemotron-pii")
    records = [
        {
            "uid": f"u{index}",
            "locale": "us",
            "document_format": "structured",
            "domain": "Life",
            "text": f"Ada wrote to ada{index}@example.com.",
            "spans": "[]",
        }
        for index in range(10)
    ]
    docs, _ = build_docs(records, spec, {"EMAIL"}, limit=3)
    assert [doc.doc_id for doc in docs] == ["u0", "u1", "u2"]


def test_the_score_is_per_document_not_a_pooled_list():
    """A prediction in one document must not match gold in another.

    A pooled list would let the hit in doc B match the gold span in doc A,
    because both sit at offsets 0 to 6.
    """

    class OnlySecondDoc:
        max_chars = 10_000
        overlap_chars = 0

        def locate(self, text, labels):
            from edgepii.protocol import Hit

            if not text.startswith("x@y.co"):
                return []
            return [Hit("email", 0, 6, None, "test.email")]

    locator = Locator.from_detectors([OnlySecondDoc()])
    docs = [
        _doc((("EMAIL", 0, 6),), "a@b.co and more"),
        _doc((), "x@y.co and more"),
    ]
    row = score_docs(locator, docs, "all", {"EMAIL"})
    assert row.tp == 0, "the hit belongs to the second document, which has no gold span"
    assert row.fn == 1
    assert row.miss == 1
    assert row.fp == 1
    assert row.extra == 1


def test_a_document_with_no_gold_and_no_hit_is_not_a_false_positive():
    locator = Locator.from_detectors([_FixedHits([])])
    docs = [_doc((), "No personal data here."), _doc((), "Nothing either.")]
    row = score_docs(locator, docs, "all", {"EMAIL"})
    payload = row.to_dict()
    assert payload["tp"] == payload["fp"] == payload["fn"] == 0
    assert payload["precision"] == 1.0
    assert payload["recall"] == 1.0


def test_a_repeated_gold_span_cannot_be_credited_twice():
    """One prediction credits one gold row, even when the corpus repeats it."""

    locator = Locator.from_detectors([_FixedHits([("EMAIL", 0, 6)])])
    docs = [_doc((("EMAIL", 0, 6), ("EMAIL", 0, 6)), "a@b.co and more")]
    row = score_docs(locator, docs, "all", {"EMAIL"})
    assert row.tp == 1
    assert row.fn == 1


def test_shift_wrong_type_and_miss_are_exclusive_and_add_up_to_fn():
    text = "Ada Lovelace called 2025550147 then ada@x.co"
    locator = Locator.from_detectors([_FixedHits([("PERSON", 0, 3), ("PHONE", 20, 30)])])
    docs = [
        _doc(
            (("PERSON", 0, 12), ("PERSON", 20, 30), ("EMAIL", 36, 46)),
            text,
        )
    ]
    row = score_docs(locator, docs, "all", {"PERSON", "PHONE", "EMAIL"})
    # PERSON 0:3 overlaps PERSON 0:12 but is shorter, so it is a shift.
    assert row.shift == 1
    # PHONE 20:30 has the same range as a gold PERSON, so it is a wrong type.
    assert row.wrong_type == 1
    # EMAIL has no prediction at all, so it is a miss.
    assert row.miss == 1
    assert row.tp == 0
    assert row.shift + row.wrong_type + row.miss == row.fn


def test_leakage_counts_a_high_severity_gold_span_that_survives():
    locator = Locator.from_detectors([_FixedHits([])])
    docs = [_doc((("PAYMENT", 0, 16), ("EMAIL", 30, 39)), "4242424242424242 then ada@x.co")]
    row = score_docs(locator, docs, "all", {"PAYMENT", "EMAIL"})
    assert row.leaks == 1


def test_report_holds_counts_not_source_text(tmp_path):
    locator = Locator.from_detectors([_FixedHits([("EMAIL", 13, 28)])])
    docs = [_doc((("EMAIL", 13, 28),), "Ada wrote to ada@example.com.")]
    row = score_docs(locator, docs, "all", {"EMAIL"})
    payload = json.dumps(row.to_dict())
    assert "ada@example.com" not in payload
    assert row.to_dict()["tp"] == 1


def test_a_locator_exposes_the_taxonomy_and_its_detectors():
    """The runner reads the type list and the class names from the locator."""

    locator = Locator.from_detectors([_FixedHits([])])
    assert locator.taxonomy.version == "2026.11"
    assert "SECRET" in locator.taxonomy.types
    assert locator.detectors


def test_a_report_names_the_class_of_each_type():
    taxonomy = load_taxonomy()
    assert taxonomy.types["PAYMENT"].class_name == "payment"
    assert taxonomy.types["PERSON"].class_name == "person"
    assert taxonomy.types["SECRET"].class_name == "secret"


class _FixedHits:
    max_chars = 10_000
    overlap_chars = 0

    def __init__(self, rows):
        self._rows = rows

    def locate(self, text, labels):
        from edgepii.protocol import Hit

        mapping = {"EMAIL": "email", "PERSON": "person", "PHONE": "phone", "PAYMENT": "card_number"}
        return [
            Hit(mapping.get(kind, kind.lower()), start, end, None, "test.fixed")
            for kind, start, end in self._rows
        ]


def _doc(spans, text):
    from edgepii.eval.corpora import Doc

    return Doc(doc_id="d", text=text, groups=(), spans=spans)


def test_bio_encoding_builds_spans_on_the_source_string():
    """A BIO corpus stores tokens. The decoder must rebuild offsets that slice."""

    record = {
        "tokens": ["Call ", "Ada ", "Lovelace", " at ", "a@b.co", "."],
        "ent_tags": ["O", "B-NAME", "I-NAME", "O", "B-EMAIL", "O"],
    }
    text = corpora.record_text({"tokens": record["tokens"], "text": None}, load_spec("spy-legal"))
    assert text == "Call Ada Lovelace at a@b.co."

    spans = corpora.bio_to_spans(record, text)
    found = {(item["label"], text[item["start"] : item["end"]]) for item in spans}
    assert ("NAME", "Ada Lovelace") in found
    assert ("EMAIL", "a@b.co") in found
    for item in spans:
        assert text[item["start"] : item["end"]].strip() == text[item["start"] : item["end"]]


def test_bio_encoding_does_not_merge_two_entities_of_one_type():
    """Two NAME entities separated by plain text stay two spans."""

    record = {
        "tokens": ["Ada ", "met ", "Grace", "."],
        "ent_tags": ["B-NAME", "O", "B-NAME", "O"],
    }
    text = "Ada met Grace."
    spans = corpora.bio_to_spans(record, text)
    assert [(text[s["start"] : s["end"]]) for s in spans] == ["Ada", "Grace"]


def test_bio_encoding_trims_the_entity_edge():
    """SPY tokens carry their trailing space. A gold span must not include it."""

    record = {"tokens": ["Email ", "a@b.co ", "now"], "ent_tags": ["O", "B-EMAIL", "O"]}
    text = "Email a@b.co now"
    spans = corpora.bio_to_spans(record, text)
    assert text[spans[0]["start"] : spans[0]["end"]] == "a@b.co"


def test_spy_materialisation_is_reproducible_for_one_seed():
    """The official loader seeds Faker. Two runs at one seed must agree."""

    pytest.importorskip("faker")
    records = [
        {
            "tokens": ["I am ", "<NAME>", " at ", "<EMAIL>", "."],
            "ent_tags": ["O", "B-NAME", "O", "B-EMAIL", "O"],
            "trailing_whitespaces": [True, False, True, False, False],
        }
    ]
    first = corpora.materialize_spy(records, seed=42)
    second = corpora.materialize_spy(records, seed=42)
    assert first[0]["tokens"] == second[0]["tokens"]
    # The placeholder must be gone and a value must be in its place.
    assert "<NAME>" not in "".join(first[0]["tokens"])
    assert "B-NAME" in first[0]["ent_tags"]
