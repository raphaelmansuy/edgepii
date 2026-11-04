"""Pure helpers for the demo. No FastAPI import here, so tests stay fast."""

from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass
from functools import lru_cache

from edgepii import DetectorLoadError, Locator, redact
from edgepii.labelmap import load_taxonomy
from edgepii.presets import PRESETS

MAX_SOURCE_CHARS = 20_000

# An extra needs every module here before the preset can load.
EXTRA_MODULES: dict[str, tuple[str, ...]] = {
    "hf": ("transformers", "torch"),
    "gliner2": ("gliner2", "torch"),
    "gliner": ("gliner", "torch"),
    "ms": ("modelscope", "torch"),
}

EXTRA_HINT = {
    "hf": "pip install -e '.[hf]'",
    "gliner2": "pip install -e '.[gliner2]'",
    "gliner": "pip install -e '.[gliner]'",
    "ms": "pip install -e '.[ms]'",
}

# A repo can need an approved Hugging Face account even when the extra is present.
GATED = {"en-bert"}

CLASS_ORDER = ("secret", "gov_id", "payment", "contact", "person", "quasi")

# Display order in the demo. Rules first, then the two default lanes.
PRESET_ORDER = ("rules", "en-closed", "multi-open", "en-bert", "phi-open", "zh-schema")

CLASS_LABEL = {
    "secret": "Secret",
    "gov_id": "Government id",
    "payment": "Payment",
    "contact": "Contact",
    "person": "Person",
    "quasi": "Quasi identifier",
}


@dataclass(frozen=True, slots=True)
class DemoError(Exception):
    """A caller mistake that the demo shows as a message, not a traceback."""

    kind: str
    message: str
    hint: str = ""


def _module_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def extra_ready(extra: str | None) -> bool:
    if extra is None:
        return True
    modules = EXTRA_MODULES.get(extra, ())
    return all(_module_present(name) for name in modules)


def presets_payload() -> list[dict]:
    rows = []
    for name, preset in PRESETS.items():
        ready = extra_ready(preset.extra)
        rows.append(
            {
                "name": name,
                "ready": ready,
                "gated": name in GATED,
                "extra": preset.extra,
                "repo_id": preset.repo_id,
                "revision": preset.revision,
                "hint": "" if ready else EXTRA_HINT.get(preset.extra or "", ""),
            }
        )
    order = {name: index for index, name in enumerate(PRESET_ORDER)}
    rows.sort(key=lambda row: order.get(row["name"], len(order)))
    return rows


def types_payload() -> list[dict]:
    taxonomy = load_taxonomy()
    rows = []
    for name, info in taxonomy.types.items():
        rows.append(
            {
                "name": name,
                "class": info.class_name,
                "rank": info.rank,
                "prefer": info.prefer,
                "default": info.class_name not in taxonomy.excluded_classes,
            }
        )
    rows.sort(key=lambda row: (row["rank"] * -1, row["name"]))
    return rows


@lru_cache(maxsize=8)
def _locator(name: str) -> Locator:
    """Keep loaded weights between requests. One entry per preset."""

    return Locator.preset(name, device="cpu")


def _valid_types(types: list[str]) -> list[str]:
    taxonomy = load_taxonomy()
    cleaned: list[str] = []
    for raw in types:
        name = str(raw).strip().upper()
        if not name:
            continue
        if name not in taxonomy.types:
            raise DemoError("unknown_type", f"Unknown type {name}.")
        if name not in cleaned:
            cleaned.append(name)
    return cleaned


def locate(
    source: str,
    preset: str,
    types: list[str],
    min_score: float | None = None,
    drop_unscored: bool = False,
) -> dict:
    if not isinstance(source, str):
        raise DemoError("bad_source", "The source must be text.")
    if len(source) > MAX_SOURCE_CHARS:
        raise DemoError(
            "too_long",
            f"The source has {len(source)} characters. The demo limit is {MAX_SOURCE_CHARS}.",
        )
    if preset not in PRESETS:
        raise DemoError("unknown_preset", f"Unknown preset {preset}.")
    wanted = _valid_types(types)
    taxonomy = load_taxonomy()

    started = time.perf_counter()
    try:
        locator = _locator(preset)
        result = locator.locate(
            source, types=wanted or None, min_score=min_score, drop_unscored=drop_unscored
        )
    except DemoError:
        raise
    except DetectorLoadError as exc:
        row = PRESETS[preset]
        raise DemoError(
            "missing_extra",
            f"Preset {preset} needs the {row.extra} extra and its weights.",
            EXTRA_HINT.get(row.extra or "", ""),
        ) from exc
    except Exception as exc:  # noqa: BLE001 - demo must not leak a traceback
        raise DemoError("locator_failed", f"{type(exc).__name__}: {exc}") from exc
    elapsed_ms = (time.perf_counter() - started) * 1000

    masked = ""
    vault_rows: list[dict] = []
    redact_error = ""
    try:
        masked, vault = redact(source, result.spans)
        vault_rows = [
            {
                "placeholder": key,
                "value": value,
                "type": _type_for_placeholder(key, result.spans),
                "secret": key == "<SECRET>",
            }
            for key, value in vault.items()
        ]
    except Exception as exc:  # noqa: BLE001 - overlaps are a guard, show them
        redact_error = f"{type(exc).__name__}: {exc}"

    class_counts: dict[str, int] = {}
    for span in result.spans:
        info = taxonomy.types[span.type]
        class_counts[info.class_name] = class_counts.get(info.class_name, 0) + 1

    rows = [
        {
            "index": position,
            "type": span.type,
            "class": taxonomy.types[span.type].class_name,
            "start": span.start,
            "end": span.end,
            "text": span.text,
            "score": span.score,
            "detector_id": span.detector_id,
            "raw_label": span.raw_label,
            "slice_ok": source[span.start : span.end] == span.text,
        }
        for position, span in enumerate(result.spans, start=1)
    ]

    return {
        "ok": True,
        "preset": result.preset,
        "revision": result.revision,
        "taxonomy_version": result.taxonomy_version,
        "elapsed_ms": round(elapsed_ms, 1),
        "source_chars": len(source),
        "dropped": result.dropped,
        "spans": rows,
        "masked": masked,
        "vault": vault_rows,
        "redact_error": redact_error,
        "class_counts": class_counts,
        "types_requested": wanted,
        "slice_ok": all(row["slice_ok"] for row in rows),
    }


def _type_for_placeholder(key: str, spans) -> str:
    prefix = key.strip("<>").rsplit("_", 1)[0]
    for span in spans:
        if span.type == prefix:
            return span.type
    return prefix
