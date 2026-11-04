"""Verify the tutorial's claims against the real library.

A tutorial that drifts from the code is worse than no tutorial. This module runs
the strings the guides show and compares the printed output with the output the
guide says to expect. It is imported by `tests/test_site.py`.

Each case is (guide, code-shape, expected output lines). The expected lines are
copied from the guide, so a change to the library that alters a result fails here
before a reader sees the wrong answer.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [PYTHON, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )


def lines(stdout: str) -> list[str]:
    return [line.rstrip() for line in stdout.strip().splitlines() if line.strip()]


# The first example on the home page and in the install guide.
FIRST_CALL = """
from edgepii import Locator

source = (
    "Customer Ada Lovelace called from +852 5555 0101. "
    "Email ada@example.com. Card 4242424242424242. Order 48291."
)

result = Locator.preset("rules").locate(source)

for span in result.spans:
    same = source[span.start:span.end] == span.text
    print(span.type, span.start, span.end, repr(span.text), same)
"""

FIRST_CALL_EXPECTED = [
    "PHONE 34 48 '+852 5555 0101' True",
    "EMAIL 56 71 'ada@example.com' True",
    "PAYMENT 78 94 '4242424242424242' True",
]

MASK_CALL = """
from edgepii import Locator, redact

source = "Email ada@example.com. Card 4242424242424242."
result = Locator.preset("rules").locate(source)
masked, vault = redact(source, result.spans)
print(masked)
print(vault)
"""

MASK_EXPECTED = [
    "Email <EMAIL_1>. Card <PAYMENT_1>.",
    "{'<EMAIL_1>': 'ada@example.com', '<PAYMENT_1>': '4242424242424242'}",
]

SECRET_CALL = """
from edgepii import Locator, redact

source = (
    "Ada Lovelace called. Email ada@example.com. "
    "Card 4242424242424242. Password: hunter2."
)
result = Locator.preset("rules").locate(source)
masked, vault = redact(source, result.spans)
print(masked)
print(sorted(vault))
"""

SECRET_EXPECTED = [
    "Ada Lovelace called. Email <EMAIL_1>. Card <PAYMENT_1>. Password: <SECRET>.",
    "['<EMAIL_1>', '<PAYMENT_1>']",
]

# The masking guide claims the vault holds no secret value.
NO_SECRET_IN_VAULT = """
from edgepii import Locator, redact

source = "Do not include the password hunter2 in the note."
result = Locator.preset("rules").locate(source)
masked, vault = redact(source, result.spans)
print(masked)
print(sorted(vault))
print("secret" if any("hunter2" in value for value in vault.values()) else "clean")
"""

NO_SECRET_EXPECTED = [
    "Do not include the password <SECRET> in the note.",
    "[]",
    "clean",
]

# The concepts page claims a repeat reuses its placeholder.
REPEAT_CALL = """
from edgepii import Locator, redact

source = "Write to ada@example.com or grace@example.com. The desk is ada@example.com."
result = Locator.preset("rules").locate(source)
masked, vault = redact(source, result.spans)
print(masked)
"""

REPEAT_EXPECTED = [
    "Write to <EMAIL_1> or <EMAIL_2>. The desk is <EMAIL_1>.",
]

# The install guide claims an order id stays unspanned.
NEGATIVE_CALL = """
from edgepii import Locator

result = Locator.preset("rules").locate("Order 48291 ships as SKU-77219 from warehouse 4.")
print(len(result.spans))
"""

NEGATIVE_EXPECTED = ["0"]

# A caller floor keeps a span that has no score, because dropping it would leave
# the value unmasked. The stricter behaviour is opt in, and the second call
# proves it.
FLOOR_CALL = """
from edgepii import Locator

source = "Email ada@example.com. Card 4242424242424242."
locator = Locator.preset("rules")
kept = [span.type for span in locator.locate(source, min_score=0.9).spans]
strict = [
    span.type for span in locator.locate(source, min_score=0.9, drop_unscored=True).spans
]
print(kept, strict)
"""

FLOOR_EXPECTED = ["['EMAIL', 'PAYMENT'] ['PAYMENT']"]

# The API page claims the offsets index the whole string after a long prefix.
LONG_CALL = """
from edgepii import Locator

prefix = "Note. " * 2000
source = prefix + "Email ada@example.com for the desk."
result = Locator.preset("rules").locate(source)
email = next(span for span in result.spans if span.type == "EMAIL")
print(source[email.start:email.end], email.start > 12_000)
"""

LONG_EXPECTED = ["ada@example.com True"]

# The API page claims empty input returns nothing rather than raising.
EMPTY_CALL = """
from edgepii import Locator

result = Locator.preset("rules").locate("")
print(result.spans, result.taxonomy_version)
"""

EMPTY_EXPECTED = ["() 2026.11"]

# The masking guide warns that a verb between the cue and the value is missed.
# Lock the behaviour, so the warning cannot go stale in either direction.
CUE_VERB_CALL = """
from edgepii import Locator

for text in ("Password: hunter2", "Password is hunter2", "password hunter2"):
    found = Locator.preset("rules").locate(text, types=["SECRET"]).spans
    print(repr(text), len(found))
"""

CUE_VERB_EXPECTED = [
    "'Password: hunter2' 1",
    "'Password is hunter2' 0",
    "'password hunter2' 1",
]

CASES = [
    ("masking guide, cue word needs no verb", CUE_VERB_CALL, CUE_VERB_EXPECTED),
    ("install guide, first call", FIRST_CALL, FIRST_CALL_EXPECTED),
    ("install guide, mask", MASK_CALL, MASK_EXPECTED),
    ("masking guide, worked example", SECRET_CALL, SECRET_EXPECTED),
    ("masking guide, no secret in vault", NO_SECRET_IN_VAULT, NO_SECRET_EXPECTED),
    ("concepts, repeated placeholder", REPEAT_CALL, REPEAT_EXPECTED),
    ("install guide, no span on an order id", NEGATIVE_CALL, NEGATIVE_EXPECTED),
    ("demo, caller floor", FLOOR_CALL, FLOOR_EXPECTED),
    ("api, long prefix offsets", LONG_CALL, LONG_EXPECTED),
    ("api, empty string", EMPTY_CALL, EMPTY_EXPECTED),
]


def failures() -> list[str]:
    """Return one message per case whose output does not match the guide."""

    problems: list[str] = []
    for name, code, expected in CASES:
        result = run(code)
        if result.returncode != 0:
            problems.append(f"{name}: raised {result.stderr.strip().splitlines()[-1] if result.stderr else 'error'}")
            continue
        actual = lines(result.stdout)
        if actual != expected:
            problems.append(f"{name}: expected {expected}, got {actual}")
    return problems


# Links in the author block. A dead link on an about page is worse than none:
# the whole point is that a reader can reach out.
AUTHOR_LINKS = [
    "https://www.linkedin.com/in/raphaelmansuy/",
    "https://github.com/raphaelmansuy",
    "https://github.com/raphaelmansuy/edgepii",
    "https://www.favikon.com/blog/top-ai-experts-france",
    "https://www.oreilly.com/library/view/the-definitive-guide/9781837631919/",
    "https://edgequake.com/",
    "https://www.edgecrab.com/",
    "https://edgewhisper.com/",
]

# The recognition line quotes Favikon. These strings must also appear on the
# Favikon page, or the claim is ours and not theirs.
FAVIKON_CLAIM = {"rank": "12", "score": "7 012"}


def author_problems(timeout: float = 15.0) -> list[str]:
    """Check the author links resolve and the Favikon claim still holds.

    Network dependent, so the suite calls this only in the site check and not on
    every test run. A failure here means a link the reader would hit is broken,
    or a number we quote has changed at the source.
    """

    import urllib.error
    import urllib.request

    problems: list[str] = []
    for url in AUTHOR_LINKS:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 edgepii-check"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status >= 400:
                    problems.append(f"author link {url} answered {response.status}")
        except urllib.error.HTTPError as exc:
            # LinkedIn answers 999 to a bot by design, and O'Reilly answers 403.
            if exc.code not in (403, 999):
                problems.append(f"author link {url} answered {exc.code}")
        except OSError as exc:
            problems.append(f"author link {url} did not answer: {exc}")

    request = urllib.request.Request(
        "https://www.favikon.com/blog/top-ai-experts-france",
        headers={"User-Agent": "Mozilla/5.0 edgepii-check"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            page = response.read().decode("utf-8", "ignore")
    except OSError as exc:
        problems.append(f"favikon did not answer: {exc}")
        return problems
    if "Mansuy" not in page:
        problems.append("the Favikon article no longer names Mansuy")
    if FAVIKON_CLAIM["score"] not in page and "7,012" not in page:
        problems.append("the Favikon score 7,012 is no longer on the page")
    return problems
