"""The quasi-identifier check.

A span list answers "which characters are personal". This answers "is this set
of ordinary fields enough to name someone". The negative cases matter as much
as the positive ones: a check that fires on every order number is noise, and a
caller will turn it off.
"""

import pytest

from edgepii import Locator, find_combinations, has_combination

_RULES = Locator.preset("rules")


# --------------------------------------------------------------------------
# The case the assessment recorded: no spans, but a person is identifiable.
# --------------------------------------------------------------------------


def test_a_zip_a_birth_date_and_a_sex_is_reported():
    source = "Patient born 1985-03-14, ZIP 94110, male, referred for follow-up."

    # The old behaviour: no span at all, because quasi types are excluded.
    assert _RULES.locate(source).spans == ()

    found = find_combinations(source)
    assert [row.name for row in found] == ["zip_dob_sex"]
    assert found[0].risk == "high"
    assert found[0].source


def test_the_result_carries_the_combination():
    source = "Patient born 1985-03-14, ZIP 94110, male."
    result = _RULES.locate(source)
    assert result.quasi
    assert result.to_dict()["quasi"][0]["name"] == "zip_dob_sex"


def test_a_pair_is_medium_risk():
    found = find_combinations("DOB 1985-03-14, postcode 94110.")
    assert [row.name for row in found] == ["zip_dob"]
    assert found[0].risk == "medium"


def test_a_birth_date_with_a_sex_is_reported():
    assert [row.name for row in find_combinations("Born 14/03/1985, female.")] == [
        "dob_sex"
    ]


def test_a_postcode_with_an_age_is_reported():
    assert [row.name for row in find_combinations("Lives at 94110, 42 years old.")] == [
        "zip_age"
    ]


def test_a_structured_postcode_needs_no_cue():
    found = find_combinations("Born 1985-03-14, SW1A 1AA, male.")
    assert [row.name for row in found] == ["zip_dob_sex"]


# --------------------------------------------------------------------------
# The check must stay quiet on ordinary text.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "Order 48291 shipped on 2026-11-04.",
        "Invoice total 1985.00 USD for SKU 12345.",
        "Meeting moved to 14 March 2027 at 10am.",
        "Call me at +852 5555 0101 about ticket 12345.",
        "The project code is 94110 and it is fine.",
        "Ada Lovelace met Grace Hopper at the lab.",
        "Version 2.1.0 released; see section 3.",
        "Delivered to SW1A 1AA on 2026-11-04.",
        "",
    ],
)
def test_ordinary_text_is_not_flagged(source):
    assert find_combinations(source) == ()
    assert not has_combination(source)


def test_a_date_needs_a_birth_cue():
    """A shipping date is not a date of birth."""

    assert find_combinations("Delivered 2026-11-04, ZIP 94110.") == ()
    assert find_combinations("Born 1985-03-14, ZIP 94110.") != ()


def test_a_bare_number_is_not_a_postcode():
    assert find_combinations("Born 1985-03-14, order 94110.") == ()
    assert find_combinations("Born 1985-03-14, postcode 94110.") != ()


def test_the_check_runs_on_the_source_not_on_the_spans():
    """The values that matter here have no public type, so spans cannot see them."""

    source = "Born 1985-03-14, ZIP 94110, male."
    result = _RULES.locate(source, types=["EMAIL"])
    assert result.spans == ()
    assert result.quasi


def test_a_non_string_is_refused():
    assert find_combinations(None) == ()
    assert find_combinations(42) == ()


def test_combination_to_dict_holds_no_value():
    import json

    payload = [row.to_dict() for row in find_combinations("Born 1985-03-14, ZIP 94110, male.")]
    text = json.dumps(payload)
    assert "1985-03-14" not in text
    assert "94110" not in text
