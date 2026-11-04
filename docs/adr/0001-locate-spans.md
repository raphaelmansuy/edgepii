# ADR 0001. Locate spans, not documents

<!-- ste: descriptive -->

Status: accepted. Date: 4 November 2026.

## Context

Callers need to mask or audit personal data in text. A document label does not name characters. A chat rewrite does not keep a check against the source string. The reasoning is Chain A in the [five whys](../00-five-whys.md).

## Decision

The library returns character spans on the source string. Each span has a type from taxonomy `2026.11`. The public contract is the [span contract](../01-span-contract.md). The library has no document-classification method.

BIO tags can exist inside an adapter. They are not the public result.

## Options rejected

| Option | Why the team rejected it |
| --- | --- |
| Bool `contains_pii` | No characters to mask or audit |
| Token ids as the result | The boundary and the mask are characters |
| Chat rewrite | No equality check against the source string |
| One label `PII` | The next action and the metrics need a type |

## Consequences

Adapters must map model output to `Hit`, then to `Span`. Eval uses exact-span F1. A feature that only improves a document-level score is out of scope.

Callers who want a bool can test `len(result.spans) > 0` themselves. The library does not add a helper that hides the spans.
