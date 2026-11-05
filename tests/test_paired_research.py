"""Hand-calculated pair outcomes; a union can cover what neither model covers."""

import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location("paired_metrics_test",Path(__file__).parents[1]/"modal/paired_metrics.py")
paired=importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)


def test_complementary_halves_recover_union_without_individual_containment():
    case=paired.case_metrics([("SECRET",0,6),("PERSON",10,13)],
        {"a":[("native",0,3),("name",10,13)],"b":[("native",3,6)]},{"SECRET"})
    result=paired.summarize([case])
    assert result["models"]["a"]["high_severity_misses"]==1
    assert result["models"]["b"]["high_severity_misses"]==1
    union=result["pairs"]["a+b"]
    assert union["high_severity_misses"]==0
    assert union["neither_alone_but_union_covers"]==1
    assert union["left_recovers_right_misses"]==1
    assert union["contained"]==2 and union["masked_characters"]==9


def test_identical_ranges_can_disagree_on_native_types_and_keep_parity():
    case=paired.case_metrics([("EMAIL",0,3)],
        {"float":[("EMAIL",0,3)],"quantized":[("CONTACT",0,3)]},set())
    pair=paired.summarize([case])["pairs"]["float+quantized"]
    assert pair["range_parity_documents"]==1
    assert pair["native_span_parity_documents"]==0
    assert pair["high_severity_misses"]==0
