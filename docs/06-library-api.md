# Public API

<!-- ste: descriptive -->

Package name: `edgepii`. Python 3.11 or newer. The result shape is the [span contract](01-span-contract.md). Types come from [taxonomy 2026.11](10-taxonomy.md). Presets come from the [catalog](05-model-catalog.md).

## Locate

```python
from edgepii import Locator

locator = Locator.preset("en-closed")
result = locator.locate(source, types=["PERSON", "EMAIL", "PHONE"])
```

| Argument | Required | Meaning |
| --- | --- | --- |
| `source` | yes | The `str` to scan. Not bytes |
| `types` | no | Subset of the taxonomy. Default: all types except class `quasi` |
| `taxonomy` | no | Default `2026.11` |
| `min_score` | no | Caller policy. Default `None`, which keeps every span. A span with no score drops when you set it. See [thresholds](10-taxonomy.md#thresholds) |

`result.taxonomy_version` is a string. `result.spans` is a tuple of `Span`. `result.dropped` is a count of hits that failed the slice check. `result.preset` is the preset name. `result.revision` is the pinned weight revision, or `rules` for the rule preset.

```python
span.type          # "EMAIL"
span.start         # int, inclusive
span.end           # int, exclusive
span.text          # source[span.start:span.end]
span.score         # float or None
span.detector_id   # "hf.antoniogr7/pii-identifier-v0.1"
span.raw_label     # "EMAIL" or "email"
```

`Span` uses a frozen dataclass. Callers cannot edit a span in place.

## Presets

| Name | Detector | Extra |
| --- | --- | --- |
| `rules` | Rules only | none |
| `en-bert` | BERT-base control plus rules | `hf` |
| `en-closed` | ModernBERT plus rules | `hf` |
| `multi-open` | GLiNER2 plus rules | `gliner2` |
| `phi-open` | NVIDIA GLiNER-PII plus rules | `gliner` |
| `zh-schema` | Siamese-UIE plus rules | `ms` |

Every preset except a future `model-only` test flag includes the rule detector. Structured types would otherwise depend on the model alone, which breaks the ladder in the [research note](04-research-landscape.md).

```python
locator = Locator.preset("multi-open", device="cpu")
```

`device` is `cpu` or `cuda`. The default is `cpu`. The library does not pick a device from a global config file.

## Redact

```python
from edgepii import redact

masked, vault = redact(source, result.spans)
```

`redact` is a pure function. It walks spans from the end of the string toward the start, so earlier indexes stay valid. It writes `<TYPE_N>` for vaulted types. It writes `<SECRET>` for class `secret`, and it does not put the secret in `vault`.

`vault` maps the placeholder to the original slice. The caller stores it. The function returns it and keeps nothing.

If two spans overlap, `redact` raises `OverlapError`. The locator must not emit overlaps. The error is a guard, not a second merger.

## Errors

| Error | When | Message contents |
| --- | --- | --- |
| `TypeError` | `source` is not a `str` | Type name only |
| `UnknownType` | A requested type is not in the taxonomy | The bad name |
| `DetectorLoadError` | Weights fail to load | Repo id and revision. No source text |
| `OverlapError` | `redact` sees an overlap | Start and end only. No slice text |
| `OffsetError` | Internal. Not raised to the caller | The locator drops the span and counts it |

INFO logs can include `detector_id`, `type`, `start`, `end`, and `score`. They must not include `source` or `span.text`. A debug flag `EDGEPII_LOG_TEXT=1` can log text. The default is off.

**WARNING:** A log line that includes `span.text` is a copy of PII. Leave the flag off in production.

## Batch

```python
results = locator.locate_many(sources, types=["EMAIL"])
```

`locate_many` preserves order. It does not join strings into one document. Offsets in each result refer to that element only. An empty element returns an empty span list.

## Windowing

Callers pass the full source string. The locator can split it inside the model adapter when the string exceeds `max_chars` for that detector. Public offsets still refer to the original source string. The split rule is in the [architecture](07-architecture.md). Callers do not pass windows.

## What the API refuses

- A method named `contains_pii` that returns only a bool. The method is a document flag.
- A method that returns token ids as the public span.
- A method that sends `source` to a URL.
- A default argument that turns on fuzzy restore.

## Minimal types

The implementation uses `@dataclass(frozen=True, slots=True)` for `Span` and `LocateResult`. No dict subclass. No pandas object in the public API. JSON export is `result.to_dict()`, and it includes `text` because the contract includes `text`. Callers who write that dict to a log copy PII. The docstring says so.
