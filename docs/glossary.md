# Glossary

<!-- ste: descriptive -->

Use these names in code, docs, and reviews. If a synonym appears in a model card, map it here and do not reuse the synonym as a public name.

| Term | Meaning |
| --- | --- |
| source string | The `str` the caller passed to `locate`. The only legal target of an offset |
| offset | A Python index into the source string. Code points, not bytes |
| span | One half-open range plus a public type, the slice, a score, a detector id, and a raw label |
| type | A name in the active taxonomy. Example: `EMAIL` |
| taxonomy | The versioned type list. Current version: `2026.11` |
| label map | The table from a raw model label to a type |
| raw label | The string the model or the rule emitted before the map |
| detector | An object that returns hits for a source string |
| hit | A private range with a raw label. Not a public span yet |
| locator | The object that maps, checks, and merges hits into a result |
| preset | A named set of detectors and a pinned revision |
| lane | A family of detectors. Rules, closed encoder, open schema, or Chinese schema |
| merger | The only module that resolves overlapping spans |
| exact-span F1 | Precision and recall where a match needs the same type, start, and end |
| miss | A gold span with no overlapping prediction |
| extra span | A prediction that overlaps no gold span |
| golden set | Labeled rows with frozen offsets. Split into a dev freeze and a sealed freeze |
| dev freeze | The golden subset builders can use to tune a caller score floor |
| sealed freeze | The golden subset for one ship decision |
| leakage | A gold high-severity slice still present at its offsets after redact |
| vault | The map from placeholder to slice. The caller holds it. The library does not |
| class | The policy group of a type. `secret`, `gov_id`, `payment`, `contact`, `person`, or `quasi` |
| UNCONFIRMED | A number or a rank with no measure on our golden set |

## Do not alternate

| Say | Do not also say |
| --- | --- |
| span | entity, hit, finding, match, as a public name |
| source string | document, text, payload, as the offset target. "text" is the slice field only |
| type | label, tag, category, as the public name. "raw label" is the private one |
| preset | model, when you mean the wired stack. The model is the checkpoint |
| locator | pipeline, engine, analyzer |
| golden set | benchmark, when you mean our freeze. A public benchmark keeps its own name |
| vault | map, in code. Prose can say "the vault". Do not also say "the store" |

PII means personally identifiable information in this set. The law can say personal data and mean a wider set. Counsel owns that wider set. The library owns the taxonomy.
