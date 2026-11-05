"""Independent BIOES examples protect the native research decoder contract."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("compact_candidates_test",
    Path(__file__).parents[1]/"modal/compact_candidates.py")
compact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compact)


@pytest.mark.parametrize("labels,expected", [
    (["B-PERSON", "I-PERSON", "E-PERSON"], [("PERSON", 0, 5)]),
    (["S-PERSON", "B-CITY", "E-CITY"], [("PERSON", 0, 1), ("CITY", 2, 5)]),
    (["I-PERSON", "E-PERSON", "O"], [("PERSON", 0, 3)]),
    (["B-PERSON", "I-CITY", "E-CITY"], [("PERSON", 0, 1), ("CITY", 2, 5)]),
    (["B-PERSON", "B-PERSON", "E-PERSON"], [("PERSON", 0, 1), ("PERSON", 2, 5)]),
])
def test_bioes_native_boundaries(labels, expected):
    source = "é 中 Z"
    hits = compact.decode_bioes(source, [(0,1),(2,3),(4,5)], labels)
    assert [(h.raw_label,h.start,h.end) for h in hits] == expected
    assert all(source[h.start:h.end] == h.claimed_text for h in hits)


def test_special_tokens_and_combining_mark_offsets():
    source = "e\u0301 Ada"
    hits = compact.decode_bioes(source, [(0,0),(0,2),(3,6),(0,0)],
                                ["O","S-PERSON","S-PERSON","O"])
    assert [(h.start,h.end,h.claimed_text) for h in hits] == [(0,2,"e\u0301"),(3,6,"Ada")]


@pytest.mark.parametrize("offsets,labels", [
    ([(0,4)],["S-X"]), ([(-1,1)],["S-X"]),
    ([(0,1)],[]), ([(0,1)],["U-X"]),
    ([(2,3),(0,1)],["B-X","I-X"]),
])
def test_bad_native_offsets_or_schema_fail(offsets, labels):
    with pytest.raises(ValueError):
        compact.decode_bioes("Ada", offsets, labels)
