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
| `min_score` | no | Caller policy. Default `None`, which keeps every span. A span with no score **survives** a floor, because a grammar match carries no probability and dropping it would leave the value unmasked. See [thresholds](10-taxonomy.md#thresholds) |
| `drop_unscored` | no | Default `False`. Set it to also remove spans that have no score. Do this only after measuring what it costs |
| `fold` | no | Default `"confusables"`. Folds invisible characters, compatibility forms, and cross-script look-alikes before matching, then maps every hit back onto the source string. Pass `False` to scan the raw text |

`result.taxonomy_version` is a string. `result.spans` is a tuple of `Span`. `result.dropped` is a count of hits that failed the slice check. `result.preset` is the preset name. `result.revision` is the pinned weight revision, or `rules` for the rule preset. `result.quasi` is a tuple of `Combination` for any re-identification risk the text carries.

`result.unmapped` counts valid model hits whose labels have no public taxonomy
mapping. The JSON export contains this count, without copying unknown labels.
It is separate from invalid offsets: a valid range can still have an
unsupported category. Neither count establishes that all PII was found.

Offsets always index `source`, never the folded text. Folding is the reason a value written with a Cyrillic `а` or a fullwidth `＠` is found at all, and the span still satisfies `source[start:end] == text`.

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
| `rules-us` | Explicit US, cue-required SSN profile plus rules | none |
| `en-bert` | BERT-base control plus rules | `hf` |
| `en-closed` | ModernBERT plus rules | `hf` |
| `multi-open` | GLiNER2 plus rules | `gliner2` |
| `multi-encoder` | Horizon Small multilingual encoder plus rules; experimental | `hf` |
| `multi-encoder-base` | Horizon Base plus rules; experimental | `hf` |
| `multi-encoder-us` | Horizon Small plus explicit US rule profile; experimental | `hf` |
| `multi-boundary` | GLiNER2.5 boundary extractor plus rules; experimental | `gliner2` |
| `phi-open` | NVIDIA GLiNER-PII plus rules | `gliner` |
| `zh-schema` | Siamese-UIE plus rules | `ms` |

Every preset except a future `model-only` test flag includes the rule detector. Structured types would otherwise depend on the model alone, which breaks the ladder in the [research note](04-research-landscape.md).

```python
locator = Locator.preset("multi-open", device="cpu")
```

`device` is `cpu` or `cuda`. The default is `cpu`. The library does not pick a device from a global config file.

## Redact

Starting in **edgepii 0.4.0**, the opt-in `locator.plan(source)` and
`redact_protected(source, plan)` retain candidate protection independently of
typed overlap selection. Plans reject dropped/unmapped diagnostics by default;
this does not certify recall. A secret taints its entire overlap component,
and exact known-secret repeats are irreversible. See the
[API, policies, and measurements](18-protection-and-model-results.md).
`protect_mapping(..., field_types={("password",): "SECRET"})` can protect
declared string fields directly and propagates known secrets across leaves.
Install or upgrade with `pip install --upgrade edgepii==0.5.0`; see the
[release and protection gate guide](21-protection-readiness.md).

```python
from edgepii import redact

masked, vault = redact(source, result.spans)
```

`redact` is a pure function. It walks spans from the end of the string toward the start, so earlier indexes stay valid. It writes `<TYPE_N>` for vaulted types. It writes `<SECRET>` for class `secret`, and it does not put the secret in `vault`.

`vault` maps the placeholder to the original slice. The caller stores it. The function returns it and keeps nothing.

If two spans overlap, `redact` raises `OverlapError`. The locator must not emit overlaps. The error is a guard, not a second merger.

## Restore

```python
from edgepii import restore

answer = restore(text, vault, locator=None, types=None)
```

`restore` is the inbound half of the loop. A model response is new text, so the only way to put the original values back is to find the placeholders the model echoed.

It returns `RestoreResult`, which is a frozen record with five fields:

| Field | Meaning |
| --- | --- |
| `text` | The restored string |
| `resolved` | Placeholders that were found and replaced |
| `unresolved` | Placeholder-shaped tokens still in the text |
| `unknown` | Spans whose text the vault never held |
| `ok` | True only when `unresolved` and `unknown` are both empty |

A placeholder resolves under case drift (`<email_1>`) and spacing drift (`< EMAIL 1 >`, `<EMAIL-1>`), because a model changes both. The longest token is replaced first, so `<EMAIL_10>` is never eaten by the `<EMAIL_1>` pattern.

Pass `locator` to also scan the raw response for PII the vault never sent. The scan runs before restoration, because restoration inserts real values on purpose.

A secret has no vault entry, so `<SECRET>` always appears in `unresolved`. That is the design: restore cannot invent a password.

## Mapping

```python
from edgepii import mask_mapping, restore_mapping

masked = mask_mapping(args, locator, types=None)
back = restore_mapping(answer, vault, locator=None, types=None)
```

`mask_mapping` walks a nested `dict` or `list`, scans each string leaf, and returns a copy with the leaves masked. The input is not modified and the structure is unchanged, so a tool still parses it.

`MaskedMapping` holds four fields:

| Field | Meaning |
| --- | --- |
| `value` | The masked tree |
| `vault` | Placeholder to original, unique across the whole tree |
| `hits` | `FieldHit` rows with a `path` and the `types` found. Never a value |
| `dropped` | Count of hits that failed the slice check |

A placeholder carries a leaf index, `<EMAIL_1_0>` and `<EMAIL_1_1>`, because two fields of the same type would otherwise both be `<EMAIL_1>` and restore would write the first value into both.

`restore_mapping` is the inbound equivalent. It returns `RestoredMapping` with `value`, `resolved`, `unresolved`, `unknown`, and `ok`.

Decode the payload before the scan. A JSON escape such as `ada\u0040example.com` holds no `@`, so a scan of the raw text misses it.

## Re-identification risk

```python
from edgepii import find_combinations, has_combination

rows = find_combinations(source)
```

A span list cannot express a combination. A postcode, a birth date, and a sex are each ordinary, and together they single out most of a population. `find_combinations` returns a `Combination` for each set it recognises, and `LocateResult.quasi` carries the same rows beside the spans.

| Field | Meaning |
| --- | --- |
| `name` | The combination, such as `zip_dob_sex` |
| `fields` | The members that were found |
| `risk` | `high` or `medium` |
| `source` | The rule that justifies the row |

A field needs evidence. A numeric postcode requires a cue word, and a date is a birth date only when the text says so. A UK outward code or a Canadian forward sortation area identifies itself.

The finding is advisory. The library does not mask a combination, because the right response depends on policy.

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

The HF and GLiNER2 adapters additionally check the actual tokenizer input
against the model context, including special tokens and GLiNER2's schema.
Each checked window advances and the windows cover the source. If even the
schema or one source character cannot fit, inference raises a source-free
`ValueError`. Processing every character does not guarantee recognition of an
entity longer than the window overlap. The optional legacy GLiNER and
ModelScope adapters have not earned the same token-coverage admission.

## What the API refuses

- A method named `contains_pii` that returns only a bool. The method is a document flag.
- A method that returns token ids as the public span.
- A method that sends `source` to a URL.
- A default argument that turns on fuzzy restore.

## Minimal types

The implementation uses `@dataclass(frozen=True, slots=True)` for `Span` and `LocateResult`. No dict subclass. No pandas object in the public API. JSON export is `result.to_dict()`, and it includes `text` because the contract includes `text`. Callers who write that dict to a log copy PII. The docstring says so.
