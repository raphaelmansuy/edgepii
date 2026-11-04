# First public score

<!-- ste: descriptive -->

This file records the first score of the shipped lanes on a public corpus. It
answers one question: does the library find PII, and where does it fail?

The run date is 4 November 2026. The host is a MacBook with an arm64 CPU and no
accelerator. Both corpora are synthetic. Every number here is a measurement on
that host, on those bytes. A number is not a ship gate. [The floors](09-evaluation.md#floors)
stay open until a sealed freeze exists.

## What ran

| Field | Value |
| --- | --- |
| Presets | `rules`, `en-closed` |
| `en-closed` revision | `3d0f39eceaf0c95fc07943064c58fba3fff60243` |
| Taxonomy | `2026.11`, eleven public types, `quasi` classes excluded |
| Corpora | `nemotron-pii` (`b70ffaf5`), `gretel-finance-en` (`7b844d16`) |
| Metric | Exact-span F1, computed per document, summed |
| Reports | `docs/eval/*.json` |

`nemotron-pii` is in domain for `en-closed`. Its card and its
`preprocessing.json` both name `nvidia/Nemotron-PII` as the training source.
`gretel-finance-en` is not in that list.

## The numbers

Micro average over every slice.

| Corpus | Preset | Docs | Gold | P | R | F1 | F2 | Leaks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `nemotron-pii` | `rules` | 2 000 | 5 890 | 0.653 | 0.266 | 0.378 | 0.301 | 589 |
| `nemotron-pii` | `en-closed` | 500 | 1 343 | 0.710 | 0.987 | 0.826 | 0.916 | 2 |
| `gretel-finance-en` | `rules` | 2 891 | 7 397 | 0.260 | 0.119 | 0.163 | 0.133 | 424 |
| `gretel-finance-en` | `en-closed` | 400 | 982 | 0.093 | 0.255 | 0.136 | 0.189 | 38 |

The `rules` F1 looks low because two of the eleven types, `PERSON` and
`ADDRESS`, hold most of the gold spans and the rule lane cannot find either
one. The [limits](../README.md#limits) already say so. The per-type table below
is the honest read of that lane.

## Per type

| Type | `rules`, Nemotron | `en-closed`, Nemotron | `rules`, Gretel | `en-closed`, Gretel |
| --- | --- | --- | --- | --- |
| `PERSON` | 0.000 | **0.995** | 0.000 | **0.048** |
| `ADDRESS` | 0.000 | 0.383 | 0.000 | 0.123 |
| `EMAIL` | 0.998 | 0.994 | 0.450 | 0.431 |
| `PHONE` | 0.644 | 0.633 | 0.351 | 0.410 |
| `PAYMENT` | 0.091 | 0.691 | 0.236 | 0.232 |
| `GOV_ID` | 0.000 | **1.000** | 0.000 | 0.321 |
| `SECRET` | 0.438 | 0.891 | 0.189 | 0.291 |
| `IP_ADDRESS` | 0.817 | 0.737 | 0.886 | 0.813 |
| `USERNAME` | 0.000 | 1.000 | 0.000 | 0.143 |

## What this shows

**The domain transfer is the finding, not the average.** `PERSON` scores 0.995
on the corpus the checkpoint trained on and 0.048 on a finance document. The
model did not learn a grammar of names. It learned where a name sits in a
synthetic persona note. A card figure of 0.9628 would have hidden that.

**The model carries the structured types that a rule cannot reach.** `GOV_ID`
scores 1.000 on Nemotron where the rule lane scores 0.000, because v1 ships no
national id pattern. The two lanes are complementary, and the preset already
runs both and merges them.

**Precision is the cost of recall.** `en-closed` reaches recall 0.987 by
masking almost every capitalised token. `ADDRESS` precision is 0.237 and
`PHONE` precision is 0.472 on Nemotron. The caller pays for that utility, and
`min_score` is the only lever the library offers, because the library ships no
floor.

**The rule lane is a floor, not a product.** Its `PAYMENT` score is 0.091 on
Nemotron. Of the 251 false positive span matches in the 2 000 document run,
150 are text that holds no gold label at all. The samples are dates such as
`2028-07-15` and bare account numbers such as `5482370169`. Both pass
`_luhn_ok`, because ISO/IEC 7812-1 sets the minimum PAN length at 8 digits and a
date in ISO 8601 form is 8 digits once the separators are dropped. A further 26
are a real `DATE_OF_BIRTH` and 56 are a real `PHONE`, so the card rule is
reaching into two other public types. Only 19 are a US SSN.

The taxonomy rank puts `GOV_ID` above `PAYMENT`, so a correct `GOV_ID` hit wins
the merge. It cannot help here, because the rule lane has no SSN rule at all,
for the reason the [rule audit](../README.md#every-rule-names-its-source)
gives: no national id pattern ships in v1. The card rule also cannot tell an
8-digit date from a PAN. That is a real gap, and this corpus made it visible.

**Two leak counts matter more than either F1.** `en-closed` leaks 2
high-severity spans on 500 Nemotron documents and 38 on 400 Gretel documents.
The parent product note says a leakage rate above zero blocks a ship. Neither
preset is ready to ship on a finance domain, and the number says why.

## What to do next

1. Decide whether an 8-digit PAN is worth keeping. ISO/IEC 7812-1 allows one,
   but a date in ISO 8601 form is also 8 digits, and 150 of the 251 `PAYMENT`
   false positives are exactly that. The rule has a correct source and a bad
   cost on real text.
2. Read twenty `PERSON` misses on Gretel. The sample is a SWIFT field and a
   signature block, not prose. That is the shape a Lane G preset should be
   tested against.
3. Add `multi-open` to the same runs. A span model with a type list at call
   time is the lane the [escalation ladder](04-research-landscape.md#escalation-ladder)
   names after `en-closed`.
4. Keep the two corpora apart. A Nemotron score and a Gretel score are two
   numbers about two corpora. Do not average them into one.

None of these steps changes a floor. The floors wait for the sealed freeze.

## The SPY benchmark

SPY is the out-of-distribution PII benchmark that the published leaderboard uses.
The legal and medical splits are Q&A forum prose and medical transcripts, so
neither split shares a template with a synthetic training corpus.

SPY ships token templates such as `<NAME>`, not values. A score therefore needs
one materialisation step. `materialize_spy` calls `Faker.seed(42)` and fills each
`B-` entity, in the same order as the official loader. The seed is fixed, so a
rerun reads the same strings. The pin still covers the template file.

| Split | Preset | Docs | Gold | P | R | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| `spy-legal` | `rules` | 4 197 | 23 128 | 0.358 | 0.298 | 0.325 |
| `spy-medical` | `rules` | 4 491 | 27 101 | 0.388 | 0.286 | 0.329 |
| `spy-legal` | `en-closed` | 200 | 1 026 | 0.183 | 0.614 | 0.281 |

The published SPY leaderboard reports exact-span F1 for other systems:
GLiNER2-PII 0.471, NVIDIA GLiNER-PII 0.391, urchade 0.384, OpenAI Privacy Filter
0.373. Those rows are measured on the 200 document slice with a label map of
their own. `en-closed` at 0.281 on 200 legal documents is below that group, and
the gap is the finding: a closed encoder trained on synthetic persona notes does
not transfer to Q&A prose.

`en-closed` reaches recall 0.614 with precision 0.183. It masks a great deal of
capitalised text, which is the behaviour the Nemotron slice also showed. The
rule lane is more precise and less complete, and the two lanes are merged in a
preset for that reason.

The `rules` row is the honest floor. It finds emails, phones, cards, IBANs and
IPs, and it never finds a name or an address. Those two types hold most of the
SPY gold, so the aggregate understates the structured types.

Run it yourself:

```bash
python -m edgepii.eval.cli --preset rules --corpus spy-legal --print
```

The report records the corpus revision and the Faker seed beside the score, so a
rerun reads the same strings.

## Comparing the two model lanes on one slice

The `multi-open` lane had never been scored. It is the lane the research
section recommends when the type list must move, and it is the same checkpoint
family as the top SPY entry, so a comparison was overdue.

Both lanes ran on the same 100 `spy-legal` documents, with the same seed and
the same taxonomy fold:

| Preset | Weights | P | R | F1 |
| --- | --- | --- | --- | --- |
| `en-closed` | ModernBERT, 0.6 GB | 0.181 | 0.622 | **0.280** |
| `multi-open` | GLiNER2, ~0.3 B params | 0.283 | 0.768 | **0.414** |

`multi-open` raises F1 by 48% relative on this slice, and it raises both
precision and recall at once. The likely reason is the shape of the task: a
span model reads the label text at inference, so the type list is a prompt
rather than a fixed class head. A closed head trained on synthetic persona
notes has to map an unseen surface form onto a class it learned, and that is
the failure the per-type table already showed for `PERSON`.

The costs are real, and they are why `en-closed` stays the default:

- Load time was 80 s on this host, against a few seconds for `en-closed`.
- Throughput was about 1.7 s per document, against 0.6 s.
- The lane needs `gliner2` and `torch`, so the install is heavier.

A caller who needs accuracy on unseen prose should start from `multi-open`. A
caller who needs a fast first pass on a frozen type list should start from
`en-closed`. Both are measured now, which is the point of this file.
