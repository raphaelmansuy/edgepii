"""The ML lane: a GLiNER classifier served by Databricks Model Serving.

This is the fourth lane. `rules` is regex and checksums, and it cannot see a
person name. `en-closed` and `multi-open` load weights inside the app process,
which is why they are not offered in the deployed demo. This lane does the
opposite: the weights live in a Databricks serving endpoint, and the app only
sends text and receives spans.

Two properties make this lane worth having alongside `rules`:

1. It finds names. The **The name gap** sample shows the rule lane leaving
   `Ada Lovelace` in the clear; this lane masks it.
2. The model call is remote, so the app stays small. No torch, no checkpoint, no
   slow first request.

The contract is narrow on purpose. The endpoint returns spans with offsets and a
label in the taxonomy's own vocabulary. This module re-checks every offset
against the text before returning it, because a remote model is exactly where an
unchecked offset would come from.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

# The endpoint returns this many characters per request comfortably. GLiNER
# degrades on very long inputs, so a caller splits beyond this.
MAX_CHARS = 8_000
DEFAULT_TIMEOUT = 60.0


class MlLaneError(Exception):
    """A failure the caller shows as a message, with the reason kept short."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True, slots=True)
class MlSpan:
    """One span from the served model, already checked against the source."""

    type: str
    start: int
    end: int
    text: str
    score: float
    raw_label: str


def _taxonomy_types() -> set[str]:
    """The types the library can actually score. A label outside this set would
    reach `taxonomy.types[...]` and fail there, far from the model that sent it."""

    from edgepii.labelmap import load_taxonomy

    return set(load_taxonomy().types)


def _clean(spans: list[dict], source: str, allowed: set[str] | None = None) -> list[MlSpan]:
    """Keep only spans that survive two checks: the type, and the slice.

    A remote model can return an offset that does not match its own text, or a
    label the taxonomy has never heard of. Both are dropped here rather than
    repaired. A label outside the taxonomy would otherwise reach
    `taxonomy.types[span.type]` and fail there, far from the cause.
    """

    kept: list[MlSpan] = []
    for row in spans:
        try:
            start = int(row["start"])
            end = int(row["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if start < 0 or end > len(source) or start >= end:
            continue
        piece = source[start:end]
        claimed = row.get("text")
        if claimed is not None and claimed != piece:
            continue
        label = str(row.get("label") or "").strip().upper()
        if not label:
            continue
        if allowed is not None and label not in allowed:
            continue
        kept.append(
            MlSpan(
                type=label,
                start=start,
                end=end,
                text=piece,
                score=float(row.get("score") or 0.0),
                raw_label=str(row.get("raw_label") or label),
            )
        )
    kept.sort(key=lambda span: (span.start, -span.end))
    return kept


def locate(
    source: str,
    *,
    host: str,
    endpoint: str,
    headers: dict[str, str],
    threshold: float | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[MlSpan]:
    """Ask the served model for spans on `source`.

    `headers` carries the caller's credentials. In the app that is the service
    principal the runtime provides; on a laptop it is the CLI's token. Neither
    is stored here.
    """

    if not source:
        return []
    if len(source) > MAX_CHARS:
        raise MlLaneError(
            "too_long",
            f"The ML lane handles {MAX_CHARS} characters per call. This text has {len(source)}.",
        )

    url = f"{host.rstrip('/')}/serving-endpoints/{endpoint}/invocations"
    body: dict = {"inputs": [source]}
    if threshold is not None:
        body["params"] = {"threshold": threshold}

    try:
        response = httpx.post(
            url,
            json=body,
            headers={**headers, "Content-Type": "application/json"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise MlLaneError("network", f"The ML lane call failed: {exc}") from exc

    if response.status_code == 403:
        raise MlLaneError(
            "forbidden",
            f"The endpoint {endpoint} refused this identity. Attach it to the app "
            f"as a serving_endpoint resource with CAN_QUERY.",
        )
    if response.status_code >= 400:
        raise MlLaneError(
            "serving",
            f"{endpoint} answered {response.status_code}. {response.text[:300]}",
        )

    payload = response.json()
    # A pyfunc endpoint returns either {"predictions": [...]} or a bare list,
    # depending on how the model was logged. Accept both rather than guess.
    predictions = payload.get("predictions", payload) if isinstance(payload, dict) else payload
    if not isinstance(predictions, list) or not predictions:
        raise MlLaneError("serving", f"{endpoint} returned no predictions.")

    first = predictions[0]
    if isinstance(first, dict):
        # A single row of columns rather than a list of spans.
        raise MlLaneError(
            "serving",
            f"{endpoint} returned a record, not a span list. Check the model signature.",
        )

    return _clean(first, source, allowed=_taxonomy_types())
