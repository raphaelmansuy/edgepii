# Span contract

<!-- ste: descriptive -->

This file is the product. Every detector, preset, and test must satisfy it. The five whys explain why the contract has this shape. See [Five whys](00-five-whys.md) and [ADR 0001](adr/0001-locate-spans.md).

## Job

Input: one source string, plus an optional subset of taxonomy types.

Output: a list of spans. Each span names a type, a start offset, an end offset, the slice text, and an optional score.

The job is location. Redaction is a pure function of those spans. The [public API](06-library-api.md) specifies redaction. It is not a second product.

## Result

```json
{
  "taxonomy_version": "2026.11",
  "spans": [
    {
      "type": "EMAIL",
      "start": 12,
      "end": 28,
      "text": "ada@example.com",
      "score": 0.99,
      "detector_id": "rules.email",
      "raw_label": "email"
    }
  ]
}
```

| Field | Rule |
| --- | --- |
| `taxonomy_version` | The taxonomy file that mapped labels for this call |
| `type` | A name in that taxonomy. Never a raw model label |
| `start` | Inclusive index into the source string |
| `end` | Exclusive index into the source string |
| `text` | Must equal `source[start:end]` |
| `score` | A float from 0 to 1, or null when the detector has no score || `detector_id` | Stable id of the detector that proposed the span |
| `raw_label` | The label before the map. For audit. Not a public type |

Indexes are Python string indexes. They count Unicode code points. They do not count UTF-8 bytes. A caller that stores bytes must convert before the call and after it.

## Invariants

A result is valid only when all of the lines below hold.

1. `0 <= start < end <= len(source)` for every span.
2. `text == source[start:end]` for every span.
3. `type` is a member of `taxonomy_version`.
4. The locator did not change the source string before it computed offsets.
5. Spans in the public list do not overlap, after the merge step in the [architecture](07-architecture.md).
6. A span whose type the caller excluded is absent from the list.
7. Exception text and INFO logs do not contain the source string or `text`.

If a detector breaks invariant 1 or 2, the locator drops that span. The locator increments a drop counter. The locator does not repair the offset by searching for `text` elsewhere in the string. A search can attach the span to the wrong copy.

## Offsets and BIO

BIO and BILOU train the head. They are not the public result. A token classifier can use them inside an adapter. The adapter must map tokens back to character offsets before it returns. The Hugging Face pipeline can do that when the tokenizer returns offsets ([token classification](https://huggingface.co/docs/transformers/en/tasks/token_classification)).

The same source string is the only legal target of those offsets. A second string, even a trimmed copy, is a defect.

## Success and failure

Success: every in-scope mention in the golden set has a span with the right type and the same start and end.

| Failure | What the caller sees | Why it matters |
| --- | --- | --- |
| Miss | No span on a gold range | The characters can leave the trust boundary |
| Wrong type | Right range, wrong type | The wrong policy runs |
| Shift | The range starts or ends on the wrong character | A tail leaks, or the mask deletes a neighbor |
| Extra span | A span on text that is not in scope | The task loses words it needed |
| Overlap | Two public spans share a character | The mask order is undefined |
| Bad slice | `text` is not `source[start:end]` | The audit is false |

A miss on a high-severity type is the costly failure. An extra span is a utility cost. The [evaluation spec](09-evaluation.md) scores them apart. It does not fold them into one unlabeled PII score.

## Jobs that are not this contract

| Job | Input | Output | Fits |
| --- | --- | --- | --- |
| PII span location | Source string | Span list | Yes |
| Document classification | Source string | has-PII or not | No |
| Regex on structured forms | Source string | Some offsets | Partial. Structured types only |
| Chat rewrite | Source string | New prose | No |
| Cloud detect API | Source string copied off the host | Vendor spans | No in v1. The copy already left. See [ADR 0003](adr/0003-local-weights.md) |

## Empty and bad input

An empty string returns an empty span list and the active taxonomy version. That result is success.

`None` is an invalid call. The library raises `TypeError`. The message does not echo a value.

A type name outside the taxonomy is an invalid call. The library raises `UnknownType`. The call does not run a detector.

## Non-goals for v1

- Image OCR. The caller passes text. A scan stays outside this library.
- A legal opinion that a type is personal data in a given country.
- Training a new checkpoint inside the library.
- A network service. The call stays inside the caller program.
- Fuzzy restore of a model answer. A fuzzy match can bind the wrong characters, so it is forbidden.
- Storage of the source string or of a reverse map. The caller holds both.

## Relation to mask and restore

The parent product is mask, then call, then restore. `edgepii` owns the first find. A small `redact` function can replace spans with placeholders and return the map to the caller. The function does not keep the map. Secrets never enter the map. See [ADR 0004](adr/0004-secrets-irreversible.md).

The outbound string is safe only when a second local pass finds no high-severity span left in it. That second pass uses the same locator. It is a product rule in the [evaluation spec](09-evaluation.md), not a new detector.
