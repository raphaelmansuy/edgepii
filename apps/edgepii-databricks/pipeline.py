"""The protect-send-restore pipeline.

One function, four stages, and every stage returns what it produced so the UI
can show the boundary between them:

1. detect   edgepii locates typed spans on the exact source string
2. mask     spans become placeholders, and the vault holds the values
3. send     the masked prompt goes to a model served by Databricks
4. restore  placeholders in the answer become the original values again

The vault never leaves this process. The UI gets the masked prompt, the raw
answer, and the restored answer. The values come back only inside the restored
answer, which is what the caller would have seen anyway.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from edgepii import Locator, redact, restore
from edgepii.labelmap import load_taxonomy

# A placeholder is angle brackets around a name: <EMAIL_1>, <SECRET>. The shape
# is the contract, so this must match `edgepii.restore`'s own pattern.
_TOKEN = re.compile(r"<[^<>\n]{1,64}>")

MAX_SOURCE_CHARS = 20_000
DEFAULT_MODEL = "databricks-gpt-oss-20b"

# The ML lane. When EDGEPII_ML_ENDPOINT is set, detection runs on a GLiNER model
# served by Databricks instead of in-process rules, and the two are unioned when
# EDGEPII_ML_WITH_RULES is on. An empty endpoint means the rules lane only.
ML_ENDPOINT_ENV = "EDGEPII_ML_ENDPOINT"
ML_THRESHOLD_ENV = "EDGEPII_ML_THRESHOLD"
ML_WITH_RULES_ENV = "EDGEPII_ML_WITH_RULES"

# Reasoning models spend the token budget on hidden reasoning before they write
# an answer, so a small max_tokens returns empty content. Ask for low effort
# and retry once with more room if the answer still comes back empty.
REASONING_MODELS = ("gpt-oss",)

SYSTEM_PROMPT = (
    "You are a support agent. Answer the ticket below in at most four sentences. "
    "Some values appear as bracketed placeholders such as <EMAIL_1> or <PHONE_1>. "
    "Copy those placeholders exactly as they appear, angle brackets included. "
    "Never invent a value for a placeholder and never guess what it stands for."
)

# One Locator per preset, so weights stay loaded between requests.
_LOCATORS: dict[str, Locator] = {}


class PipelineError(Exception):
    """A caller mistake the UI shows as a message, not a traceback."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True, slots=True)
class ModelCall:
    """What the serving endpoint sent back, plus how long it took."""

    content: str
    reasoning: str
    model: str
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None


def models() -> list[str]:
    """Serving endpoints this app offers, from EDGEPII_MODELS."""

    raw = os.environ.get("EDGEPII_MODELS", DEFAULT_MODEL)
    names = [name.strip() for name in raw.split(",") if name.strip()]
    return names or [DEFAULT_MODEL]


def ml_endpoint() -> str:
    """The detector endpoint, or an empty string when the ML lane is off."""

    return os.environ.get(ML_ENDPOINT_ENV, "").strip()


def ml_threshold() -> float:
    raw = os.environ.get(ML_THRESHOLD_ENV, "").strip()
    try:
        return float(raw) if raw else 0.4
    except ValueError:
        return 0.4


def ml_with_rules() -> bool:
    """Union the ML lane with the rule lane. Default on: rules prove some types."""

    raw = os.environ.get(ML_WITH_RULES_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def lanes() -> list[dict]:
    """What the UI offers. A lane is a detection method, not a model choice."""

    rows = [
        {
            "name": "rules",
            "label": "Rules",
            "note": "Regex and checksums. No weights, no network. Cannot see a name.",
            "ready": True,
        }
    ]
    endpoint = ml_endpoint()
    if endpoint:
        rows.append(
            {
                "name": "ml",
                "label": "GLiNER (served)",
                "note": f"Pretrained classifier on {endpoint}. Finds names.",
                "ready": True,
            }
        )
        if ml_with_rules():
            rows.append(
                {
                    "name": "hybrid",
                    "label": "Rules + GLiNER",
                    "note": "Both lanes, unioned. Rules win where they are certain.",
                    "ready": True,
                }
            )
    return rows


def locator(preset: str) -> Locator:
    cached = _LOCATORS.get(preset)
    if cached is None:
        cached = Locator.preset(preset)
        _LOCATORS[preset] = cached
    return cached


def _client() -> Any:
    """A WorkspaceClient that works in the app and on a laptop.

    In a Databricks App the runtime injects DATABRICKS_CLIENT_ID and
    DATABRICKS_CLIENT_SECRET for the app service principal. Locally the SDK
    falls back to the profile named by DATABRICKS_PROFILE.
    """

    from databricks.sdk import WorkspaceClient

    if os.environ.get("DATABRICKS_CLIENT_ID"):
        return WorkspaceClient()
    profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
    try:
        return WorkspaceClient(profile=profile)
    except Exception as exc:  # noqa: BLE001 - one actionable message beats a stack
        raise PipelineError(
            "auth",
            f"No Databricks credentials for profile {profile!r}. Run "
            f"`databricks auth login --profile {profile}` and try again, or set "
            f"DATABRICKS_PROFILE to a profile that already works. "
            f"({type(exc).__name__}: {exc})",
        ) from exc


def _invoke(model: str, messages: list[dict], max_tokens: int) -> ModelCall:
    """POST to the serving endpoint's OpenAI-compatible route."""

    try:
        client = _client()
        headers = dict(client.config.authenticate())
        host = (client.config.host or "").rstrip("/")
    except Exception as exc:  # noqa: BLE001 - config errors are a demo message
        raise PipelineError("auth", f"Cannot build Databricks credentials: {exc}") from exc

    if not host:
        raise PipelineError("auth", "No workspace host. Set DATABRICKS_HOST.")

    url = f"{host}/serving-endpoints/{model}/invocations"
    body: dict[str, Any] = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    if any(name in model for name in REASONING_MODELS):
        body["reasoning_effort"] = "low"

    started = time.perf_counter()
    try:
        response = httpx.post(
            url,
            json=body,
            headers={**headers, "Content-Type": "application/json"},
            timeout=120.0,
        )
    except httpx.HTTPError as exc:
        raise PipelineError("network", f"Serving endpoint call failed: {exc}") from exc
    latency_ms = (time.perf_counter() - started) * 1000

    if response.status_code == 403:
        raise PipelineError(
            "forbidden",
            f"{model} refused this identity. In a Databricks App, attach the "
            f"endpoint as a resource with CAN_QUERY. Locally, the profile needs "
            f"CAN_QUERY on the endpoint too. ({response.text[:200]})",
        )
    if response.status_code >= 400:
        raise PipelineError(
            "serving",
            f"{model} answered {response.status_code}. {response.text[:400]}",
        )

    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        raise PipelineError("serving", f"{model} returned no choices.")

    message = choices[0].get("message") or {}
    usage = payload.get("usage") or {}
    return ModelCall(
        content=(message.get("content") or "").strip(),
        reasoning=(message.get("reasoning_content") or "").strip(),
        model=payload.get("model") or model,
        latency_ms=round(latency_ms, 1),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )


def _ml_spans(source: str, headers: dict[str, str]) -> tuple[list, dict]:
    """Run the ML lane and return (spans, timing). Imported lazily on purpose.

    The rules lane must keep working when the ML lane is unset, so nothing here
    is allowed to fail at import time.
    """

    try:
        try:
            import ml_lane
        except ModuleNotFoundError:  # imported as a package from the repo root
            from apps.edgepii_databricks import ml_lane  # type: ignore[no-redef]
    except Exception as exc:  # noqa: BLE001 - a missing module is a demo message
        raise PipelineError("lane_unavailable", f"The ML lane is not available: {exc}") from exc

    endpoint = ml_endpoint()
    started = time.perf_counter()
    found = ml_lane.locate(
        source,
        host=_host_or_raise(),
        endpoint=endpoint,
        headers=headers,
        threshold=ml_threshold(),
    )
    elapsed = (time.perf_counter() - started) * 1000

    from edgepii.span import Span

    spans = [
        Span(
            type=row.type,
            start=row.start,
            end=row.end,
            text=row.text,
            score=row.score,
            detector_id=f"serving.{endpoint}",
            raw_label=row.raw_label,
        )
        for row in found
    ]
    return spans, {"ml_ms": round(elapsed, 1)}


def _host_or_raise() -> str:
    try:
        client = _client()
        host = client.config.host or ""
    except PipelineError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PipelineError("auth", f"Cannot read the workspace host: {exc}") from exc
    if not host:
        raise PipelineError("auth", "No workspace host. Set DATABRICKS_HOST.")
    return host.rstrip("/")


def _headers_or_raise() -> dict[str, str]:
    try:
        client = _client()
        return dict(client.config.authenticate())
    except PipelineError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PipelineError("auth", f"Cannot build Databricks credentials: {exc}") from exc


def _detect(source: str, preset: str, lane: str) -> tuple[object, dict]:
    """Detect spans on `source` for one lane, returning (result, timing).

    `rules` runs the in-process detectors. `ml` runs the served classifier.
    `hybrid` runs both and merges through the library's own policy, so the rule
    lane keeps precedence on the types the taxonomy marks `prefer: rule`.
    """

    timings: dict = {}

    if lane == "rules":
        started = time.perf_counter()
        try:
            result = locator(preset).locate(source)
        except Exception as exc:  # noqa: BLE001
            raise PipelineError("locate_failed", f"{type(exc).__name__}: {exc}") from exc
        timings["detect_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return result, timings

    if not ml_endpoint():
        raise PipelineError("lane_unavailable", "The ML lane is not configured.")

    headers = _headers_or_raise()

    if lane == "ml":
        spans, ml_timing = _ml_spans(source, headers)
        return _result_from_ml(source, spans, preset), ml_timing

    # hybrid: rules first, then ML, then one merge through the taxonomy policy.
    started = time.perf_counter()
    try:
        rules_result = locator(preset).locate(source)
    except Exception as exc:  # noqa: BLE001
        raise PipelineError("locate_failed", f"{type(exc).__name__}: {exc}") from exc
    rules_ms = (time.perf_counter() - started) * 1000

    ml_spans, ml_timing = _ml_spans(source, headers)

    from edgepii.labelmap import load_taxonomy
    from edgepii.merge import merge_spans

    taxonomy = load_taxonomy()
    combined = list(rules_result.spans) + list(ml_spans)
    allowed = {span.type for span in combined}
    merged = tuple(merge_spans(combined, taxonomy, allowed))

    return (
        _rebuild_result(rules_result, merged, preset),
        {
            "detect_ms": round(rules_ms + ml_timing.get("ml_ms", 0.0), 1),
            "ml_ms": ml_timing.get("ml_ms", 0.0),
            "raw_rules": len(rules_result.spans),
            "raw_ml": len(ml_spans),
        },
    )


def _result_from_ml(source: str, spans: list, preset: str):
    """A LocateResult carrying only ML spans. Offsets are already checked."""

    from edgepii.labelmap import load_taxonomy
    from edgepii.span import LocateResult

    taxonomy = load_taxonomy()
    ordered = tuple(sorted(spans, key=lambda span: (span.start, span.end, span.type)))
    return LocateResult(
        taxonomy_version=taxonomy.version,
        spans=ordered,
        dropped=0,
        preset=f"{preset}+ml",
        revision="serving",
    )


def _rebuild_result(rules_result, spans: tuple, preset: str):
    """Keep the rule result's metadata, swap in the merged span list."""

    from edgepii.span import LocateResult

    return LocateResult(
        taxonomy_version=rules_result.taxonomy_version,
        spans=spans,
        dropped=rules_result.dropped,
        preset=f"{preset}+ml",
        revision=rules_result.revision,
        quasi=rules_result.quasi,
        unmapped=rules_result.unmapped,
    )



def _tokens_in(text: str) -> set[str]:
    """Every placeholder-shaped token in a string."""

    return {match.group() for match in _TOKEN.finditer(text)}


def _segments(raw: str, vault: dict[str, str]) -> list[dict]:
    """Split the raw answer so the UI can mark exactly what came from the vault.

    The pattern mirrors `edgepii.restore`: a placeholder is case-insensitive and
    tolerant of spaces or dashes where the underscore was. Doing this here, not
    in the browser, keeps the highlighted characters equal to the restored ones.
    """

    if not raw:
        return []

    ordered = sorted(vault.items(), key=lambda pair: len(pair[0]), reverse=True)
    found: list[tuple[int, int, str]] = []
    for token, _value in ordered:
        inner = token[1:-1].strip()
        parts = [part for part in re.split(r"[\s_\-]+", inner) if part]
        body = r"[\s_\-]*".join(re.escape(part) for part in parts) if parts else ""
        pattern = re.compile(r"<\s*" + body + r"\s*>", re.IGNORECASE)
        for match in pattern.finditer(raw):
            found.append((match.start(), match.end(), token))

    # Drop overlaps: a longer token already claimed the range.
    found.sort(key=lambda row: (row[0], -row[1]))
    kept: list[tuple[int, int, str]] = []
    for start, end, token in found:
        if kept and start < kept[-1][1]:
            continue
        kept.append((start, end, token))

    segments: list[dict] = []
    cursor = 0
    for start, end, token in kept:
        if start > cursor:
            segments.append({"kind": "text", "text": raw[cursor:start]})
        segments.append({"kind": "value", "text": vault[token], "placeholder": token})
        cursor = end
    if cursor < len(raw):
        segments.append({"kind": "text", "text": raw[cursor:]})
    return segments


def run(
    source: str,
    model: str = DEFAULT_MODEL,
    preset: str = "rules",
    max_tokens: int = 400,
    scan_response: bool = True,
    lane: str = "rules",
) -> dict:
    """Run all four stages and return one payload for the UI.

    `lane` chooses how detection works: `rules` in-process, `ml` on the served
    classifier, `hybrid` both merged. `model` is the generator and is independent
    of the lane, because detecting PII and writing a reply are different jobs.
    """

    if not isinstance(source, str) or not source.strip():
        raise PipelineError("bad_source", "Add some text first.")
    if len(source) > MAX_SOURCE_CHARS:
        raise PipelineError(
            "too_long",
            f"The source has {len(source)} characters. The demo limit is {MAX_SOURCE_CHARS}.",
        )
    if model not in models():
        raise PipelineError("bad_model", f"{model} is not in EDGEPII_MODELS.")
    available = {row["name"] for row in lanes()}
    if lane not in available:
        raise PipelineError(
            "bad_lane",
            f"Lane {lane!r} is not available. Choose one of: {', '.join(sorted(available))}.",
        )

    taxonomy = load_taxonomy()

    # Stage 1: detect. The lane decides how; the result shape does not change.
    result, detect_timing = _detect(source, preset, lane)
    detect_ms = detect_timing.get("detect_ms", 0.0)


    # Stage 2: mask. A secret type is irreversible, so it never enters the vault.
    started = time.perf_counter()
    try:
        masked, vault = redact(source, result.spans)
    except Exception as exc:  # noqa: BLE001 - overlapping spans land here
        raise PipelineError("redact_failed", f"{type(exc).__name__}: {exc}") from exc
    mask_ms = (time.perf_counter() - started) * 1000

    # Stage 3: send. Only the masked string crosses the network.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": masked},
    ]
    call = _invoke(model, messages, max_tokens)
    if not call.content:
        # A reasoning model can spend the whole budget thinking and return no
        # answer. One retry with a floor is cheaper than a dead demo.
        call = _invoke(model, messages, max(max_tokens, 1200))
    if not call.content:
        raise PipelineError(
            "empty_answer",
            f"{model} returned an empty answer. Try a different model or a higher token budget.",
        )

    # Stage 4: restore. The vault maps placeholders back to values.
    started = time.perf_counter()
    probe = locator(preset) if scan_response else None
    outcome = restore(
        call.content,
        vault,
        locator=probe,
        types=None if scan_response else [],
    )
    restore_ms = (time.perf_counter() - started) * 1000

    # A secret type is irreversible, so `redact` emits <SECRET> and keeps the
    # value out of the vault. That token staying in the answer is the intended
    # outcome, not a failure. Separate it from tokens we cannot explain.
    sealed = sorted(
        token for token in _tokens_in(masked) if token not in vault
    )
    unresolved = list(outcome.unresolved)
    expected = [token for token in unresolved if token in sealed]
    unexplained = [token for token in unresolved if token not in sealed]

    spans = [
        {
            "index": position,
            "type": span.type,
            "class": taxonomy.types[span.type].class_name,
            "start": span.start,
            "end": span.end,
            "text": span.text,
            "score": span.score,
            "detector_id": span.detector_id,
            "slice_ok": source[span.start : span.end] == span.text,
        }
        for position, span in enumerate(result.spans, start=1)
    ]

    class_counts: dict[str, int] = {}
    for span in result.spans:
        label = taxonomy.types[span.type].class_name
        class_counts[label] = class_counts.get(label, 0) + 1

    return {
        "ok": True,
        "model": call.model,
        "preset": preset,
        "lane": lane,
        "source": source,
        "spans": spans,
        "span_count": len(spans),
        "class_counts": class_counts,
        "masked": masked,
        "vault": [{"placeholder": key, "value": value} for key, value in vault.items()],
        "raw_answer": call.content,
        "reasoning": call.reasoning,
        "answer": outcome.text,
        "segments": _segments(call.content, vault),
        "resolved": list(outcome.resolved),
        "unresolved": unexplained,
        "sealed": expected,
        "unknown": [
            {"type": span.type, "text": span.text, "start": span.start, "end": span.end}
            for span in outcome.unknown
        ],
        "restore_ok": not unexplained and not outcome.unknown,
        "slice_ok": all(row["slice_ok"] for row in spans),
        "tokens": {
            "prompt": call.prompt_tokens,
            "completion": call.completion_tokens,
        },
        "timing": {
            "detect_ms": round(detect_ms, 1),
            "mask_ms": round(mask_ms, 1),
            "model_ms": call.latency_ms,
            "restore_ms": round(restore_ms, 1),
            "total_ms": round(detect_ms + mask_ms + call.latency_ms + restore_ms, 1),
            "ml_ms": round(detect_timing.get("ml_ms", 0.0), 1),
        },
    }
