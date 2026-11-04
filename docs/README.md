# edgepii specification

<!-- ste: descriptive -->

Status: implemented. This set records the problem, the research, the public API, and the build plan. The library, the tests, and the demo now follow this set. See the [project README](../README.md) for install and quickstart.

`edgepii` is a Python library that locates personally identifiable information (PII) in text. The library returns typed character spans on the same string the caller passed. The library does not decide that a whole document is sensitive.

This set records the problem, the research, the public API, and the build plan. Card scores in the research notes are not ship gates. See the [evaluation spec](09-evaluation.md).

## Read this set in order

1. [Five whys](00-five-whys.md). The problem, one cause at a time.
2. [Span contract](01-span-contract.md). The only result the library can return.
3. [First principles](02-first-principles.md). Rules that stay true when models change.
4. [AI engineering](03-ai-engineering.md). How the team chooses and rejects a model.
5. [Research landscape](04-research-landscape.md). Papers and lanes, as of November 2026.
6. [Model catalog](05-model-catalog.md). Hugging Face and ModelScope candidates.
7. [Taxonomy](10-taxonomy.md). The versioned type list and the label maps.
8. [Public API](06-library-api.md). Call shapes and errors.
9. [Examples](11-examples.md). Fake text that shows each preset.
10. [Public corpora](12-public-corpora.md). The pinned PII sets and the label fold.
11. [First public score](13-first-public-score.md). Two lanes, two corpora, measured.
12. [Architecture](07-architecture.md). Modules, DRY, and SOLID.
13. [Implementation plan](08-implementation-plan.md). Build order and acceptance tests.
14. [Evaluation](09-evaluation.md). Exact-span F1, slices, and ship gates.
15. [Glossary](glossary.md). One name for each concept.

Decisions:

- [ADR 0001, locate spans](adr/0001-locate-spans.md)
- [ADR 0002, two default lanes](adr/0002-two-default-lanes.md)
- [ADR 0003, local weights in v1](adr/0003-local-weights.md)
- [ADR 0004, secrets stay irreversible](adr/0004-secrets-irreversible.md)

## Decision in one page

Keep a locator that returns `{type, start, end, text, score}` on the source string. Ship two default lanes after a frozen golden set, not before it.

| Lane | Preset | Weights | Use when |
| --- | --- | --- | --- |
| Closed encoder | `en-closed` | [antoniogr7/pii-identifier-v0.1](https://huggingface.co/antoniogr7/pii-identifier-v0.1) | The team freezes the type list, the text is English, and latency matters |
| Open schema | `multi-open` | [fastino/gliner2-privacy-filter-PII-multi](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi) | The caller must change types at call time |

A classic BERT control stays available as preset `en-bert` ([ab-ai/pii_model](https://huggingface.co/ab-ai/pii_model)). BERT-family token classification is enough when the taxonomy and the domain stay fixed. See [when the encoder is enough](04-research-landscape.md#when-the-encoder-is-enough).

Rules for email, phone, IBAN, and payment cards run beside the model. They do not replace it for names. Chinese schema extraction is an optional ModelScope adapter, not a default. See the [catalog](05-model-catalog.md).

## Assessment, November 2026

The library is at 0.2.0. It locates spans, masks them, and restores them, and the
span contract holds. The [assessment](14-assessment-2026-11.md) records what is
measured, three defects that a reader can reproduce, and where the field moved
ahead of the library: the tool-call plane, surrogate replacement, and
quasi-identifier combinations.

## What v1 will not do

V1 will not send the source string to a cloud PII API. V1 will not ask a chat model to rewrite the text. V1 will not treat a document label as success. V1 will not copy a leaderboard F1 into a ship gate. The numeric floors stay open until the golden set exists. Call that open state UNCONFIRMED.

## Terms

Use the names in the [glossary](glossary.md). Do not rename a span to an entity, a hit, or a finding in this set.
