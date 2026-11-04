"""Detect a combination of fields that re-identifies a person.

A span list answers "which characters are personal". It cannot answer "is this
set of ordinary fields enough to name someone", because each field is benign
alone. A postcode, a date of birth, and a sex identify most of a population
when they appear together. That is Sweeney's k-anonymity result, and it is the
reason a per-span mask can be complete and still unsafe.

This module reads a span list, or a decoded mapping, and reports each
combination it recognises. It does not mask anything. A caller decides what to
do with the finding: mask the whole set, generalise one field, or refuse.

The patterns are explicit and each names its source, the same rule the rest of
the library follows. A threshold with no source does not ship.

Sources:

- Sweeney, "k-anonymity: a model for protecting privacy" (2002) for the
  ZIP + date of birth + sex combination.
- GDPR Article 4(1) treats a combination of identifiers as personal data when
  it can single a person out.
- The pattern set and the risk levels follow the three-field test that
  SurrogateShield uses for its quasi-identifier scorer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A postcode in the forms a ticket usually carries. A bare five-digit number is
# not evidence: it is an order id as often as it is a ZIP. So a numeric postcode
# needs a cue word, and only the unmistakable national formats stand alone.
_POSTCODE_CUE = re.compile(
    r"(?i)\b(?:zip|zipcode|zip\s*code|postcode|post\s*code|postal\s*code|"
    r"resides?\s+in|resident\s+of|address|live[sd]?\s+at)\b"
)
_US_ZIP = re.compile(r"(?<![\w-])\d{5}(?:-\d{4})?(?![\w-])")
# A UK outward code or a Canadian forward sortation area has letters and digits
# in a fixed shape, so it identifies itself.
_STRUCTURED_POSTCODE = re.compile(
    r"(?<![\w-])(?:[A-Z]{1,2}\d[A-Z\d]?|[A-Z]\d[A-Z])(?![\w-])"
)

# A date of birth needs a birth cue. A shipping date is not a birth date.
_DOB_CUE = re.compile(r"(?i)\b(?:born|dob|d\.o\.b|date\s+of\s+birth|birth\s*date|birthday)\b")
_DATE = re.compile(
    r"(?<![\w-])("
    r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}"  # 1985-03-14
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"  # 14/03/1985
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?:19|20)\d{2}"
    r")(?![\w-])",
    re.IGNORECASE,
)

# A sex or gender token, as a word, not inside another word.
_SEX = re.compile(r"(?<![\w-])(?:male|female|man|woman|boy|girl)(?![\w-])", re.IGNORECASE)

_AGE = re.compile(r"(?<![\w-])(\d{1,3})\s*(?:years?\s+old|yrs?\s+old|years?\s+of\s+age)(?![\w-])", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Combination:
    """One recognised set of fields that can single a person out.

    `fields` names what was found. `risk` is `high` when the set is close to a
    unique identifier on its own, and `medium` when it needs a small background
    population to finish the job. `source` is the rule that justifies the row.
    """

    name: str
    fields: tuple[str, ...]
    risk: str
    source: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fields": list(self.fields),
            "risk": self.risk,
            "source": self.source,
        }


def _found(text: str) -> dict[str, bool]:
    has_cue = bool(_POSTCODE_CUE.search(text))
    return {
        # A numeric postcode needs a cue. A structured code identifies itself.
        "postcode": bool(_STRUCTURED_POSTCODE.search(text))
        or (has_cue and bool(_US_ZIP.search(text))),
        # A date is a date of birth only when the text says so.
        "date_of_birth": bool(_DOB_CUE.search(text)) and bool(_DATE.search(text)),
        "sex": bool(_SEX.search(text)),
        "age": bool(_AGE.search(text)),
    }


def find_combinations(text: str) -> tuple[Combination, ...]:
    """Return every quasi-identifier combination present in `text`.

    The check runs on the text, not on a span list, because the values that
    matter here are the ones the taxonomy excludes: a postcode and a date of
    birth carry no public type by default.
    """

    if not isinstance(text, str) or not text:
        return ()
    present = _found(text)
    rows: list[Combination] = []

    if present["postcode"] and present["date_of_birth"] and present["sex"]:
        rows.append(
            Combination(
                name="zip_dob_sex",
                fields=("postcode", "date_of_birth", "sex"),
                risk="high",
                source="Sweeney 2002. Five-digit ZIP, date of birth, and sex identify most of a US population.",
            )
        )
    elif present["postcode"] and present["date_of_birth"]:
        rows.append(
            Combination(
                name="zip_dob",
                fields=("postcode", "date_of_birth"),
                risk="medium",
                source="Sweeney 2002. The pair narrows a population sharply and is one field short of a unique row.",
            )
        )
    elif present["date_of_birth"] and present["sex"]:
        rows.append(
            Combination(
                name="dob_sex",
                fields=("date_of_birth", "sex"),
                risk="medium",
                source="Sweeney 2002. A birth date and a sex are two of the three fields in the classic combination.",
            )
        )

    if present["postcode"] and present["age"]:
        rows.append(
            Combination(
                name="zip_age",
                fields=("postcode", "age"),
                risk="medium",
                source="GDPR Article 4(1). A postcode with an exact age narrows a population the same way a birth date does.",
            )
        )
    return tuple(rows)


def has_combination(text: str) -> bool:
    return bool(find_combinations(text))
