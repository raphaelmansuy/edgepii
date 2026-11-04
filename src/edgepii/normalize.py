"""Fold look-alike characters for matching, then report offsets on the source.

A detector that reads raw text is blind to a homoglyph. A Cyrillic ``а``
(U+0430) renders exactly like a Latin ``a``, so an address written with one
looks correct to a reviewer and matches no pattern.

This module folds text into a matchable form and keeps a map back to the source
index of every folded character. The locator runs the detectors on the folded
text, then translates each hit back onto the source string. The public span
therefore still satisfies the span contract:

    source[span.start:span.end] == span.text

and the span covers the obfuscated characters, so a mask removes all of them.

Three kinds of folding apply, in this order:

1. **Invisible characters** are dropped. A zero-width space inside an address
   is not a character a reader can see, so it must not break a match.
2. **Compatibility forms** fold through NFKC. This turns fullwidth digits and
   ``＠`` into their ASCII forms.
3. **Cross-script confusables** fold through a small table of the characters
   that appear in real obfuscation. NFKC does not do this, because a Cyrillic
   ``а`` is a legitimate letter in its own script.

The table is deliberately small and explicit. A large automatic skeleton would
change text a caller did not ask to change, and the mapping must stay
predictable for the offsets to be defensible.
"""

from __future__ import annotations

import unicodedata

# Zero-width and other invisible characters. A reader cannot see them, so they
# never belong inside a match.
_INVISIBLE = frozenset(
    {
        "\u200b",  # zero width space
        "\u200c",  # zero width non-joiner
        "\u200d",  # zero width joiner
        "\u2060",  # word joiner
        "\u2061",
        "\u2062",
        "\u2063",
        "\u2064",
        "\ufeff",  # zero width no-break space
        "\u00ad",  # soft hyphen
        "\u180e",  # mongolian vowel separator
    }
)

# Cross-script confusables that NFKC leaves alone. Each entry is a character from
# another script that renders like the Latin letter named in the comment.
_CONFUSABLES: dict[str, str] = {
    # Cyrillic lowercase
    "\u0430": "a",
    "\u0435": "e",
    "\u043e": "o",
    "\u0440": "p",
    "\u0441": "c",
    "\u0443": "y",
    "\u0445": "x",
    "\u0456": "i",
    "\u0458": "j",
    "\u0455": "s",
    "\u0501": "d",
    "\u04bb": "h",
    "\u043a": "k",
    "\u043c": "m",
    "\u043d": "h",
    "\u0442": "t",
    "\u0432": "b",
    # Cyrillic uppercase
    "\u0410": "A",
    "\u0412": "B",
    "\u0415": "E",
    "\u041a": "K",
    "\u041c": "M",
    "\u041d": "H",
    "\u041e": "O",
    "\u0420": "P",
    "\u0421": "C",
    "\u0422": "T",
    "\u0425": "X",
    "\u0406": "I",
    "\u0408": "J",
    "\u0405": "S",
    # Greek
    "\u03b1": "a",
    "\u03bf": "o",
    "\u03bd": "v",
    "\u03b9": "i",
    "\u03ba": "k",
    "\u03c1": "p",
    "\u03c5": "u",
    "\u0391": "A",
    "\u0392": "B",
    "\u0395": "E",
    "\u0396": "Z",
    "\u0397": "H",
    "\u0399": "I",
    "\u039a": "K",
    "\u039c": "M",
    "\u039d": "N",
    "\u039f": "O",
    "\u03a1": "P",
    "\u03a4": "T",
    "\u03a5": "Y",
    "\u03a7": "X",
    # Latin small capitals and Roman numerals that render as letters
    "\u2170": "i",
    "\u217c": "l",
    "\u217d": "c",
    "\u217e": "d",
    "\u217f": "m",
    # Dashes that a reader sees as a hyphen
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
}

# Characters that fold to one character through NFKC but are not letters, such as
# the fullwidth at sign. NFKC handles them, and no table entry is needed.

DEFAULT_FOLD = "confusables"


class Folded:
    """Folded text plus the source index of every folded character.

    `offsets[i]` is the index in the source string of the character that became
    folded character `i`. A dropped character has no entry, which is how a span
    can extend over invisible characters.
    """

    __slots__ = ("text", "offsets", "changed")

    def __init__(self, text: str, offsets: list[int], changed: bool) -> None:
        self.text = text
        self.offsets = offsets
        self.changed = changed

    def to_source(self, start: int, end: int) -> tuple[int, int]:
        """Translate a half-open range on the folded text to the source string."""

        if start >= end or not self.offsets:
            return start, end
        if start < 0 or end > len(self.offsets):
            return start, end
        first = self.offsets[start]
        last = self.offsets[end - 1]
        return first, last + 1


def _fold_char(char: str) -> str:
    """Return the matchable form of one character, or an empty string to drop it."""

    if char in _INVISIBLE:
        return ""
    if char in _CONFUSABLES:
        return _CONFUSABLES[char]
    # NFKC folds compatibility forms: fullwidth, ligatures, Roman numerals that
    # have a canonical compatibility mapping.
    folded = unicodedata.normalize("NFKC", char)
    if folded == char:
        return char
    # A single character may fold to several. They all point at the source index.
    if folded in _INVISIBLE:
        return ""
    return folded


def fold(source: str) -> Folded:
    """Fold `source` for matching and record where every character came from."""

    if not source:
        return Folded("", [], False)

    chars: list[str] = []
    offsets: list[int] = []
    changed = False
    for index, char in enumerate(source):
        folded = _fold_char(char)
        if folded != char:
            changed = True
        for out in folded:
            chars.append(out)
            offsets.append(index)
    return Folded("".join(chars), offsets, changed)


def needs_fold(source: str) -> bool:
    """True when the source holds a character this module would change."""

    for char in source:
        if char in _INVISIBLE or char in _CONFUSABLES:
            return True
        if unicodedata.normalize("NFKC", char) != char:
            return True
    return False
