"""Put the original values back into a model response. The caller owns the vault.

`redact` is the outbound half of the loop. This is the inbound half. A model
response is new text, so the only way to restore it is to find the placeholders
the model echoed and swap them back.

Three failure modes matter, and each one is reported rather than hidden:

1. The model changed the case or the spacing of a placeholder. A lower-case
   ``<email_1>`` is still the token we sent, so the match is case-insensitive
   and tolerant of spaces inside the brackets.
2. The model invented a placeholder we never sent, or kept one we cannot map.
   That token would reach the user as noise, so it is counted as unresolved.
3. The model produced PII that was never in the vault. That is a leak or a
   hallucination, and a redaction pipeline should refuse it. Pass a locator and
   this function reports those spans.

A placeholder pair such as ``<EMAIL_1>`` and ``<EMAIL_10>`` is why the longest
token is replaced first. Replacing the short one first would corrupt the long
one, and a corrupted token cannot be restored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from edgepii.span import Span

# A placeholder is angle brackets around a name, optionally with a space:
# <EMAIL_1>, < SECRET >, <PERSON_12>. The shape is the contract, not a type list.
_PLACEHOLDER = re.compile(r"<[^<>\n]{1,64}>")
_SPACE_RUN = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class RestoreResult:
    """The restored text, plus every token this function could not resolve.

    `text` is safe to show when `ok` is true. When `ok` is false, the caller
    should treat the response as a partial result: a placeholder may still be
    visible, or the model may have produced PII the vault never held.
    """

    text: str
    resolved: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    unknown: tuple[Span, ...] = field(default=())

    @property
    def ok(self) -> bool:
        """True when every placeholder resolved and no unknown PII appeared."""

        return not self.unresolved and not self.unknown

    def to_dict(self) -> dict:
        """Export the outcome. `unknown` carries text, so this dict copies PII."""

        return {
            "text": self.text,
            "resolved": list(self.resolved),
            "unresolved": list(self.unresolved),
            "unknown": [span.to_dict() for span in self.unknown],
            "ok": self.ok,
        }


def _pattern_for(token: str) -> re.Pattern[str]:
    """Match one placeholder, allowing case and spacing drift inside the brackets.

    A model may lower-case a token, space the brackets, or replace the underscore
    with a space. All three still name the value we sent, so all three resolve.
    `EMAIL 1`, `email_1`, and ` EMAIL_1 ` are one token here.
    """

    inner = token[1:-1].strip()
    # Split on the separator, then allow any run of separator characters between
    # the parts. This handles "EMAIL_1", "EMAIL 1", "EMAIL-1", and "EMAIL  1".
    parts = [part for part in re.split(r"[\s_\-]+", inner) if part]
    body = r"[\s_\-]*".join(re.escape(part) for part in parts) if parts else ""
    return re.compile(r"<\s*" + body + r"\s*>", re.IGNORECASE)


def restore(
    text: str,
    vault: dict[str, str],
    *,
    locator=None,
    types: list[str] | None = None,
) -> RestoreResult:
    """Replace every placeholder the model echoed with its original value.

    `vault` is the mapping `redact` returned. The function keeps nothing.

    Pass `locator` to also scan the model output for PII that the vault never
    held. That check costs one extra detector pass, and it is the difference
    between "we masked the prompt" and "we checked the response".
    """

    if not isinstance(text, str):
        raise TypeError(type(text).__name__)
    if not isinstance(vault, dict):
        raise TypeError(type(vault).__name__)

    # Longest first: <EMAIL_10> must be replaced before <EMAIL_1>.
    ordered = sorted(vault.items(), key=lambda pair: len(pair[0]), reverse=True)

    restored = text
    resolved: list[str] = []
    for token, value in ordered:
        pattern = _pattern_for(token)
        restored, count = pattern.subn(lambda _match, v=value: v, restored)
        if count:
            resolved.append(token)

    unresolved = _unresolved_tokens(restored)
    unknown = _unknown_pii(text, vault, locator, types)

    return RestoreResult(
        text=restored,
        resolved=tuple(resolved),
        unresolved=unresolved,
        unknown=unknown,
    )


def _unresolved_tokens(text: str) -> tuple[str, ...]:
    """Placeholder-shaped tokens still in the text after every replacement."""

    found: dict[str, None] = {}
    for match in _PLACEHOLDER.finditer(text):
        token = _SPACE_RUN.sub(" ", match.group()).strip()
        found.setdefault(token, None)
    return tuple(found)


def _unknown_pii(text: str, vault: dict[str, str], locator, types) -> tuple[Span, ...]:
    """PII in the raw model output that the vault never sent.

    The scan runs on the model's own text, before restoration, because
    restoration inserts real values by design. A value found here was produced
    by the model or echoed from a part of the prompt the mask missed.
    """

    if locator is None:
        return ()

    known = {_norm_value(value) for value in vault.values()}
    if not known:
        return ()

    result = locator.locate(text, types=types) if types else locator.locate(text)
    return tuple(span for span in result.spans if _norm_value(span.text) not in known)


def _norm_value(value: str) -> str:
    return _SPACE_RUN.sub(" ", value).strip().casefold()
