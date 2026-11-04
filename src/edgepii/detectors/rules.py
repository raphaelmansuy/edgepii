"""Structured forms with a named validator.

Every rule here answers one question: does a published grammar or checksum
confirm this slice? A rule that a validator confirms scores 1.0. A rule that
only matches a shape scores null. No rule invents a probability.
"""

from __future__ import annotations

import ipaddress
import re

import phonenumbers
from phonenumbers import PhoneNumberMatcher, ValidationResult

from edgepii.protocol import Hit

# RFC 5321 section 4.5.3.1: local part at most 64 octets, path at most 256.
# The domain must hold at least one dot and a two-letter top label.
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"([A-Za-z0-9!#$%&'*+/=?^_`{|}~\-]{1,64}"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~\-]{1,64})*)"
    r"@"
    r"((?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63})"
    r"(?![A-Za-z0-9\-])"
)

# ISO/IEC 7812-1: a PAN holds 8 to 19 digits and starts with a major industry
# identifier in the range 1 to 9. Separators are spaces or hyphens.
_CARD = re.compile(r"(?<![A-Za-z0-9])\d(?:[ \-]?\d){7,18}(?![A-Za-z0-9])")

# ISO 13616: two country letters, two check digits, then 11 to 30 alphanumerics.
_IBAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}[A-Z0-9]{11,30}(?![A-Za-z0-9])")

# RFC 3986 section 3.2.2 for IPv4 text form. Octet ranges are checked by value.
# A trailing sentence period is allowed. A trailing digit or dotted octet is not.
_IPV4 = re.compile(r"(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9])(?!\.[0-9])")

# RFC 4291 section 2.2 text forms. The stdlib validator decides membership.
_IPV6 = re.compile(r"(?<![0-9A-Za-z:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Za-z:])")

# A cue word, then one of two forms.
#   1. Assignment: cue, separator, value. The separator marks the value.
#   2. Mention: cue, space, value, where the value holds a digit or a symbol.
# Form 2 exists because prose says "the password hunter2". A bare word after a
# cue is prose, so form 2 refuses it. That is a grammar rule, not a word list.
_CUE_ASSIGN = re.compile(
    r"(?i)\b(?:password|passcode|passwd|api[_\-]?key|access[_\-]?token|secret[_\-]?key)\b"
    r"\s*[:=]\s*"
    r"([^\s,.;:=\"'()<>\[\]]{1,256})"
)
_CUE_MENTION = re.compile(
    r"(?i)\b(?:password|passcode|passwd|api[_\-]?key|access[_\-]?token|secret[_\-]?key)\b"
    r"\s+"
    r"([^\s,.;:=\"'()<>\[\]]{1,256})"
)
_SECRET_SHAPE = re.compile(r"[0-9!-/:-@\[-`{-~]")

# ISO 3166 regions that the phone rule asks libphonenumber to try.
PHONE_REGIONS = ("US", "CN", "HK", "GB")


def _luhn_ok(digits: str) -> bool:
    """ISO/IEC 7812-1 check digit."""

    if not 8 <= len(digits) <= 19:
        return False
    if digits[0] == "0":
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = ord(char) - 48
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _iban_ok(raw: str) -> bool:
    """ISO 13616 with the ISO 7064 MOD-97-10 check."""

    compact = raw.replace(" ", "").upper()
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    number = ""
    for char in rearranged:
        if char.isdigit():
            number += char
        elif "A" <= char <= "Z":
            number += str(ord(char) - 55)
        else:
            return False
    return int(number) % 97 == 1


def _ip_ok(raw: str) -> bool:
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        return False
    return True


class RuleDetector:
    """Validators and grammars. Person names are not this detector's job."""

    max_chars = 10_000_000
    overlap_chars = 0
    detector_kind = "rules"

    def locate(self, source: str, labels: list[str]) -> tuple[Hit, ...]:
        allowed = {_norm(label) for label in labels}
        hits: list[Hit] = []
        if _wants(allowed, "email"):
            hits.extend(_emails(source))
        if _wants(allowed, "phone", "phone_number", "phonenumber"):
            hits.extend(_phones(source))
        if _wants(allowed, "card_number", "payment_card", "creditcardnumber", "credit_debit_card", "iban", "bank_account"):
            hits.extend(_payments(source, allowed))
        if _wants(allowed, "ip", "ip_address", "ipv4", "ipv6"):
            hits.extend(_ips(source))
        if _wants(allowed, "password", "passcode", "secret", "api_key", "access_token", "secret_key"):
            hits.extend(_secrets(source))
        return tuple(hits)


def _norm(label: str) -> str:
    return label.strip().casefold().replace(" ", "_")


def _wants(allowed: set[str], *names: str) -> bool:
    return any(name in allowed for name in names)


def _emails(source: str) -> list[Hit]:
    """RFC 5322 address in its common ASCII form. Shape only, so score is null."""

    hits = []
    for match in _EMAIL.finditer(source):
        if len(match.group()) > 254:
            continue
        hits.append(Hit("email", match.start(), match.end(), None, "rules.email"))
    return hits


def _phones(source: str) -> list[Hit]:
    """libphonenumber decides. Two accept tests, one per documented form.

    A number that libphonenumber calls valid is a phone. A number that starts
    with an explicit international prefix and has a plan-correct length is a
    phone. Nothing else is. The region list only supplies a default region.
    """

    found: dict[tuple[int, int], float | None] = {}
    for region in PHONE_REGIONS:
        matcher = PhoneNumberMatcher(
            source, region, leniency=phonenumbers.Leniency.POSSIBLE
        )
        for match in matcher:
            key = (match.start, match.end)
            text = source[match.start : match.end]
            if phonenumbers.is_valid_number(match.number):
                found[key] = 1.0
                continue
            if not text.startswith("+"):
                continue
            reason = phonenumbers.is_possible_number_with_reason(match.number)
            if reason == ValidationResult.IS_POSSIBLE:
                found.setdefault(key, None)
    return [
        Hit("phone", start, end, score, "rules.phone")
        for (start, end), score in sorted(found.items())
    ]


def _payments(source: str, allowed: set[str]) -> list[Hit]:
    hits: list[Hit] = []
    iban_spans: list[tuple[int, int]] = []
    if _wants(allowed, "iban", "bank_account"):
        for match in _IBAN.finditer(source):
            if not _iban_ok(match.group()):
                continue
            iban_spans.append((match.start(), match.end()))
            hits.append(Hit("iban", match.start(), match.end(), 1.0, "rules.iban"))
    if _wants(allowed, "card_number", "payment_card", "creditcardnumber", "credit_debit_card"):
        for match in _CARD.finditer(source):
            if _inside(match.start(), match.end(), iban_spans):
                continue
            raw = match.group()
            digits = "".join(char for char in raw if char.isdigit())
            if not _luhn_ok(digits):
                continue
            hits.append(Hit("card_number", match.start(), match.end(), 1.0, "rules.card"))
    return hits


def _inside(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(left <= start and end <= right for left, right in spans)


def _ips(source: str) -> list[Hit]:
    hits: list[Hit] = []
    for pattern in (_IPV4, _IPV6):
        for match in pattern.finditer(source):
            if not _ip_ok(match.group()):
                continue
            hits.append(Hit("ip_address", match.start(), match.end(), 1.0, "rules.ip"))
    return hits


def _secrets(source: str) -> list[Hit]:
    """A cue names a value. An assignment always counts, a mention needs a shape."""

    spans: dict[tuple[int, int], Hit] = {}
    for match in _CUE_ASSIGN.finditer(source):
        key = (match.start(1), match.end(1))
        spans[key] = Hit("password", key[0], key[1], None, "rules.secret")
    for match in _CUE_MENTION.finditer(source):
        value = match.group(1)
        if _SECRET_SHAPE.search(value) is None:
            continue
        key = (match.start(1), match.end(1))
        spans.setdefault(key, Hit("password", key[0], key[1], None, "rules.secret"))
    return [spans[key] for key in sorted(spans)]
