# Evaluation

<!-- ste: descriptive -->

The scorer exists before the adapters. See phase 1 of the [implementation plan](08-implementation-plan.md) and principle 1 in [AI engineering](03-ai-engineering.md).

## Primary metric

Exact-span F1. A prediction is a true positive only when `type`, `start`, and `end` equal a gold span. The rule is CoNLL exact entity match, on character spans ([W03-0419](https://aclanthology.org/W03-0419/)). SeqScore's cautions on double-counting still apply ([2021.eval4nlp-1.5](https://aclanthology.org/2021.eval4nlp-1.5/)). One gold span can credit one prediction.

Report the metric per type and as a micro average. Do not report a single bucket named PII. Macro F1 is a diagnostic. It is not the ship metric, because rare types would dominate it.

## Diagnostics

| Name | Definition | Role |
| --- | --- | --- |
| Miss | Gold span with no overlapping prediction of any type | Leak candidate |
| Wrong type | Overlap, exact range or not, with a different type | Policy miss |
| Shift | Same type, overlap, not exact | Boundary bug |
| Extra span | Prediction that overlaps no gold span | Utility cost |
| Token F1 | Token tags, inside an adapter test | Debug only. Not a ship gate |

Partial overlap is not a true positive for the ship metric. It is a shift or a wrong type.

F2 (beta = 2) is a second column for high-severity types. Presidio's own guidance favors recall when the cost is a leak ([FAQ](https://github.com/microsoft/presidio/blob/main/docs/faq.md)). F2 does not replace exact-span F1. It explains a threshold move.

## Leakage

Leakage is a product metric on the string a later step would send. For a gold span, the span leaks when `span.text` still occurs in the masked string at the gold offsets. The check uses offsets, not a global search, so a repeated token elsewhere is not a false leak.

`edgepii` can compute this because `redact` is pure. The eval harness runs `locate`, then `redact`, then the leakage check. High-severity classes for this check are `secret`, `gov_id`, and `payment`.

The parent product note says that a high-severity leakage rate above zero on the freeze means that the team must not ship ([Hide names and phones](https://app.notion.com/p/407887c3416481daa9a7e3ce8b346775)). This spec keeps that gate for the masked string on the sealed freeze. It does not claim a model has no misses. If the model misses and the rule lane also misses, the preset does not ship. The mitigation is a better detector or a refusal to send, not a softer score.

The downstream task owns its utility floors. This spec leaves those floors open.

## Sets

| Set | Who can read it | Use |
| --- | --- | --- |
| Unit fixtures | Everyone | Fake strings in [Examples](11-examples.md) |
| Public corpus | Everyone | A pinned open PII set. [Public corpora](12-public-corpora.md) |
| Dev freeze | Builders who tune | Thresholds, error reading |
| Sealed freeze | One run per promotion | Ship decision. No tuning after the run starts |

The public corpus replaced the plan to write a freeze from scratch. `nemotron-pii` is the in-domain slice and `gretel-finance-en` is the out-of-domain slice, and both carry a commit revision, a byte count, and a `sha256` in [corpora.yaml](../src/edgepii/eval/corpora.yaml). A run that does not match the pin stops. Two people can score the same preset and get the same number.

A public corpus is not the sealed freeze. It is public, so a checkpoint can train on it. The sealed freeze still needs a human-read slice of the real channel.

Split synthetic rows by template id. Split real rows by document id. A template in both train and test is an eval failure, even if F1 rises. The locate note and the builder note both require this split.

The dev freeze must include at least these slices:

| Slice | What it holds |
| --- | --- |
| `structured` | Email, phone, IBAN, Luhn card, one bad PAN |
| `names` | Two people, one person, a person who is also a street name |
| `secrets` | A fake password next to an email |
| `negative` | An order id, a SKU, a public company name with ORG disabled |
| `long_doc` | A gold email past the first window |
| `zh` | Optional. Fake Chinese contact line. Required only for phase 10 |

Start the dev freeze from public synthetic spans (Nemotron-PII, OpenPII, SPY) plus rows you write. Tag every row with `source_corpus` and `template_id`. Do not put n2c2 or other DUA text in the repo.

A human must read the dev freeze before the first sealed run. Model drafts are not gold. Do not edit gold to match a model.

## Floors

Until phase 9 writes numbers, every floor stays open. Phase 9 sets them from the dev freeze in a commit that does not include the sealed scores. Then the sealed run uses those numbers unchanged.

The kinds of floors, with no fake targets:

| Floor | Kind |
| --- | --- |
| Exact-span recall for `PAYMENT`, `GOV_ID`, `EMAIL`, `PHONE` | Minimum on the sealed freeze |
| Exact-span recall for `PERSON` | Minimum. Expected to be the hard type |
| Extra-span rate on `negative` | Maximum |
| High-severity leakage after redact | 0 on the sealed freeze, from the parent gate |
| p95 locate latency on CPU for a 2_000 character note | Maximum. Host-specific. UNCONFIRMED |

Do not copy 0.96 from a card into the recall floor. That number is in-domain for someone else's split.

## Report

Each run writes a JSON report: preset, revision, taxonomy version, per-type counts, leakage, and the slice name. The report omits source strings. A local HTML or text dump for error reading can include text. That dump stays out of git when the text is not from the fake examples.

The harness is `python -m edgepii.eval.cli`. It takes a preset, a corpus key, an optional limit, and an optional type subset. The report lands in `docs/eval/`. [Public corpora](12-public-corpora.md) documents every field.

Compare presets on the same gold file. Two different gold files do not make a valid compare. The research note shows why: SPY tables already disagree with each other. A Nemotron score and a Gretel score are two different numbers about two different corpora. Neither one wins.

A run must score one document at a time. A pooled list of every gold span would let a prediction in one document match gold in another, and the report would claim a hit for text that document does not hold. `tests/test_eval_corpora.py` locks the case.

## Contamination checks

<!-- ste: procedural -->

1. Hash each template id in the sealed freeze.
2. If that id appears in a train list you used to fine-tune, fail the run.
3. If a builder opened the sealed file in the same change as a threshold edit, fail the run.
4. Record the git revision of the scorer next to the score.

V1 does not fine-tune. Check 2 is still required. A public checkpoint can train on OpenPII or Nemotron-PII.

When the preset card lists that corpus, mark the slice `in_domain`. Do not use an `in_domain` slice as the only ship gate. Keep one slice the card does not list. SPY is the public candidate for that slice. Our own ticket-shaped fake rows are the other.

## What is not an eval

| Practice | Why it fails |
| --- | --- |
| LLM-as-judge for spans | The match is code |
| One screenshot | No counts |
| Micro F1 on a fixture of three emails | No names, no negatives |
| A vendor F1 with no gold file in the repo | Not replayable |
