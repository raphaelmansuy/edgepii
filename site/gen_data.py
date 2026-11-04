"""Precompute real library output for the static site.

A GitHub Pages site cannot run Python. This script runs the real `edgepii`
library once, here, and records the exact spans it returns. The site then
replays that record. Nothing on the site is a mock: every row is a number the
library produced, with the offset proof `source[start:end] == text` intact.

Two lanes are recorded per example where the weights are present:

- `rules`, which needs no download and always works
- `en-closed`, the ModernBERT lane, when the `hf` extra and the weights exist

The browser can then filter the recorded spans by type and by score floor. That
filter is faithful, because the library applies the same two rules: drop a span
whose type is not allowed, and drop a span whose score is below the caller
floor. A span with `score = None` cannot meet a floor, so a floor drops it.

Regenerate with `make site-data`. The output is committed, so CI stays light.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from edgepii import Locator, redact  # noqa: E402
from edgepii.labelmap import load_taxonomy  # noqa: E402
from edgepii.presets import PRESETS  # noqa: E402

OUT = HERE / "data" / "examples.json"

# Every string is fake. Do not replace one with production text.
EXAMPLES: list[dict] = [
    {
        "id": "support-ticket",
        "title": "A support ticket",
        "blurb": "A phone number, an email, and a test card. The order id stays clear.",
        "why": "Three structured forms, each confirmed by a grammar or a checksum. `Order 48291` is not PII, so it stays visible.",
        "tags": ["EMAIL", "PHONE", "PAYMENT"],
        "text": (
            "Customer Ada Lovelace called from +852 5555 0101. "
            "Email ada@example.com. Card 4242424242424242. Order 48291."
        ),
    },
    {
        "id": "secret-note",
        "title": "A note with a password",
        "blurb": "The password is masked. It never enters the vault.",
        "why": "A secret is irreversible on purpose. Restoring it would write a password into the next system.",
        "tags": ["SECRET", "EMAIL", "PHONE"],
        "text": (
            "Ask Ada Lovelace <ada@example.com> to call +1 202 555 0147 "
            "about ticket 77. Do not include the password hunter2 in the note."
        ),
    },
    {
        "id": "payments",
        "title": "A wire transfer",
        "blurb": "A valid IBAN is found. A card that fails Luhn is ignored.",
        "why": "The IBAN passes the MOD-97 check. `4242424242424243` fails Luhn, so the rule refuses it rather than guessing.",
        "tags": ["PAYMENT", "EMAIL", "IP_ADDRESS"],
        "text": (
            "Wire to IBAN GB82WEST12345698765432 from card 4242424242424243. "
            "Reach ops at ops@example.org or 203.0.113.10."
        ),
    },
    {
        "id": "chinese",
        "title": "A Chinese contact line",
        "blurb": "A Chinese mobile number and an email, on the rule lane.",
        "why": "The rule lane is language neutral for structured forms. The phone still passes libphonenumber.",
        "tags": ["PHONE", "EMAIL"],
        "text": "联系人张伟，手机13800138000，邮箱wei@example.com。",
    },
    {
        "id": "placeholders",
        "title": "Two people, two placeholders",
        "blurb": "A repeat reuses its token. A new slice gets a new number.",
        "why": "The same address twice gets `<EMAIL_1>` twice. A second address gets `<EMAIL_2>`.",
        "tags": ["EMAIL"],
        "text": (
            "Write to ada@example.com or grace@example.com. "
            "The desk address is ada@example.com."
        ),
    },
    {
        "id": "negatives",
        "title": "Text with no PII",
        "blurb": "An order id, a SKU, and a plain sentence.",
        "why": "These look numeric, and none is a published PII form. A locator that spans them is guessing.",
        "tags": [],
        "text": (
            "Order 48291 ships as SKU-77219 from warehouse 4. "
            "The build finished in 12 minutes on node 3."
        ),
    },
    {
        "id": "long-text",
        "title": "Long text, original offsets",
        "blurb": "The email sits far into the string. The offset still indexes the whole source.",
        "why": "A long document is split into windows internally. The public offset is never a window offset.",
        "tags": ["EMAIL"],
        "text": "Note. " * 60 + "Email ada@example.com for the desk.",
    },
    {
        "id": "logs",
        "title": "A log line",
        "blurb": "An IP address and an email inside a structured line.",
        "why": "An IP address passes an RFC 4291 or RFC 3986 match and then a stdlib parse.",
        "tags": ["IP_ADDRESS", "EMAIL"],
        "text": (
            "2026-11-04T09:12:33Z level=warn user=ada@example.com "
            "src=198.51.100.7 path=/v1/orders action=denied"
        ),
    },
    {
        "id": "prompt",
        "title": "A prompt before it leaves",
        "blurb": "What a caller sends to a model after masking.",
        "why": "This is the product case: keep the sentence, remove the person, prove which characters left.",
        "tags": ["EMAIL", "PERSON", "SECRET"],
        "text": (
            "Summarise this for the on-call engineer: Ada Lovelace reported that "
            "ada@example.com cannot reset the password hunter2 from Lisbon."
        ),
    },
    {
        "id": "names",
        "title": "Two names",
        "blurb": "A person name needs a model lane. The rule lane finds neither.",
        "why": "A name has no grammar and no checksum. Rules own structured forms, models own names.",
        "tags": ["PERSON"],
        "text": "Ada Lovelace met Grace Hopper at the lab to review the schedule.",
    },
    {
        "id": "address",
        "title": "A postal address",
        "blurb": "A street address, a person, and an email together.",
        "why": "An address is a model type. The email beside it is a rule type. The locator merges both.",
        "tags": ["ADDRESS", "PERSON", "EMAIL"],
        "text": (
            "Ship the replacement to Grace Hopper, 12 Rue de Rivoli, Paris. "
            "Confirm on grace@example.com before Friday."
        ),
    },
    {
        "id": "gov-id",
        "title": "A national id",
        "blurb": "A US SSN pattern. The rule lane is silent, and the model lane is not.",
        "why": "V1 ships no national id pattern, by design. This row shows what the model lane buys.",
        "tags": ["GOV_ID", "PERSON"],
        "text": "Applicant Ada Lovelace, SSN 121-45-6789, signed the form today.",
    },
    {
        "id": "account",
        "title": "An account handle",
        "blurb": "A login name, which is not a display name.",
        "why": "`USERNAME` is a model type. It is the string that marks an account, not the person.",
        "tags": ["USERNAME", "EMAIL"],
        "text": "User lkernan signed in and asked to reset access for lkernan@example.com.",
    },
    {
        "id": "finance",
        "title": "A finance note",
        "blurb": "A card, a routing number, and a name in a bank context.",
        "why": "The hardest case in the public score. A finance document does not look like a persona note.",
        "tags": ["PAYMENT", "PERSON", "EMAIL"],
        "text": (
            "The transfer from Grace Hopper uses card 5490 3479 1287 6543 "
            "and routing number 271210785. Receipt to grace@example.com."
        ),
    },
]


def main() -> int:
    taxonomy = load_taxonomy()
    default_types = taxonomy.default_types()
    available = _extras_present()
    lanes = [name for name in ("rules", "en-closed") if name == "rules" or "hf" in available]

    # A machine without the hf extra can still regenerate the rule lane. Keep the
    # lane rows the committed file already holds, so CI does not drop the model
    # lane from a build that has no weights.
    previous = _previous_examples()
    dropped = sorted({"en-closed"} - set(lanes))

    locators: dict[str, Locator] = {}
    for lane in lanes:
        try:
            locators[lane] = Locator.preset(lane, device="cpu")
        except Exception as exc:  # noqa: BLE001 - a missing lane must not stop the build
            print(f"note: lane {lane} did not load: {type(exc).__name__}", file=sys.stderr)

    rows: list[dict] = []
    for example in EXAMPLES:
        text = example["text"]
        lane_rows: dict[str, dict] = {}
        for lane, locator in locators.items():
            result = locator.locate(text)
            masked, vault = redact(text, result.spans)
            lane_rows[lane] = {
                "spans": [_span_row(span, taxonomy) for span in result.spans],
                "masked": masked,
                "vault": [{"placeholder": key, "value": value} for key, value in vault.items()],
                "dropped": result.dropped,
                "revision": result.revision,
            }
        for lane in dropped:
            kept = (previous.get(example["id"]) or {}).get("lanes", {}).get(lane)
            if kept:
                lane_rows[lane] = kept
        rows.append(
            {
                "id": example["id"],
                "title": example["title"],
                "blurb": example["blurb"],
                "why": example["why"],
                "tags": example["tags"],
                "text": text,
                "chars": len(text),
                "lanes": lane_rows,
            }
        )

    recorded = sorted({name for row in rows for name in row["lanes"]})
    # Keep a fixed display order: the lane with no download first, so a reader is
    # never shown a model result as if it were the default case.
    lane_order = ["rules", "en-closed", "multi-open", "en-bert", "phi-open", "zh-schema"]
    recorded = [name for name in lane_order if name in recorded]
    for row in rows:
        row["lanes"] = {name: row["lanes"][name] for name in lane_order if name in row["lanes"]}
    payload = {
        "generated_by": "site/gen_data.py",
        "taxonomy_version": taxonomy.version,
        "default_types": default_types,
        "types": [
            {
                "name": name,
                "class": info.class_name,
                "rank": info.rank,
                "prefer": info.prefer,
                "default": info.class_name not in taxonomy.excluded_classes,
            }
            for name, info in sorted(taxonomy.types.items(), key=lambda row: (-row[1].rank, row[0]))
        ],
        "lanes": [
            {
                "name": name,
                "label": _lane_label(name),
                "revision": PRESETS[name].revision,
                "repo_id": PRESETS[name].repo_id,
                "note": _lane_note(name),
            }
            for name in recorded
        ],
        "examples": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(rows)} examples and lanes {recorded}")
    if dropped:
        print(f"note: kept the recorded {dropped} lane from the previous run", file=sys.stderr)
    return 0


def _span_row(span, taxonomy) -> dict:
    return {
        "type": span.type,
        "class": taxonomy.types[span.type].class_name,
        "start": span.start,
        "end": span.end,
        "text": span.text,
        "score": span.score,
        "detector_id": span.detector_id,
        "raw_label": span.raw_label,
    }


def _previous_examples() -> dict[str, dict]:
    if not OUT.is_file():
        return {}
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {row["id"]: row for row in data.get("examples", [])}


def _extras_present() -> set[str]:
    present = set()
    for name, modules in {
        "hf": ("transformers", "torch"),
        "gliner2": ("gliner2", "torch"),
        "gliner": ("gliner", "torch"),
        "ms": ("modelscope", "torch"),
    }.items():
        import importlib.util

        if all(importlib.util.find_spec(module) is not None for module in modules):
            present.add(name)
    return present


def _lane_label(name: str) -> str:
    return {
        "rules": "Rules and checksums",
        "en-closed": "Closed encoder (ModernBERT)",
        "multi-open": "Open schema (GLiNER2)",
        "en-bert": "BERT control",
        "phi-open": "Health-adjacent (GLiNER)",
        "zh-schema": "Chinese schema (UIE)",
    }.get(name, name)


def _lane_note(name: str) -> str:
    return {
        "rules": "No weights, no download. Patterns and checksums only, so names stay out.",
        "en-closed": "Local ModernBERT weights. Finds names and addresses as well as structured forms.",
        "multi-open": "Takes the type list at call time.",
        "en-bert": "BERT control for comparison.",
        "phi-open": "Health-adjacent labels.",
        "zh-schema": "Chinese text through schema prompts.",
    }.get(name, name)


if __name__ == "__main__":
    raise SystemExit(main())
