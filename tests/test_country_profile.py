"""US ID profile tests: explicit country, cue, structural exclusions, no probabilities."""

import pytest

from edgepii import Locator
from edgepii.detectors.rules import RuleDetector


def test_default_rules_do_not_silently_enable_a_country_profile():
    source="SSN: 123-45-6789"
    assert not Locator.preset("rules").locate(source,types=["GOV_ID"]).spans
    spans=Locator.preset("rules-us").locate(source,types=["GOV_ID"]).spans
    assert [(s.type,s.text,s.score) for s in spans] == [("GOV_ID","123-45-6789",None)]


@pytest.mark.parametrize("value",["000-12-3456","666-12-3456","900-12-3456","123-00-3456","123-12-0000"])
def test_structural_exclusions_are_not_positive_recognitions(value):
    assert not Locator.preset("rules-us").locate("SSN: "+value,types=["GOV_ID"]).spans


@pytest.mark.parametrize("source",["Order 123-45-6789", "123-45-6789", "SSN policy uses order 123-45-6789"])
def test_shape_alone_is_not_enough(source):
    assert not Locator.preset("rules-us").locate(source,types=["GOV_ID"]).spans


def test_unicode_folding_keeps_original_country_rule_offsets():
    source="SSN: １２３-４５-６７８９"
    spans=Locator.preset("rules-us").locate(source,types=["GOV_ID"]).spans
    assert len(spans)==1 and source[spans[0].start:spans[0].end] == spans[0].text


def test_unsupported_country_is_explicit():
    with pytest.raises(ValueError,match="unsupported"):RuleDetector(gov_id_country="XX")
