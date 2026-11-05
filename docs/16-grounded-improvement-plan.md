# Grounded improvement plan

Research cutoff: **5 November 2026**. Evidence:
[research update](15-research-update-2026-11.md),
[model manifest](research/model-manifest-2026-11-05.json), and
[historical assessment](14-assessment-2026-11.md).

This plan separates implementable engineering changes from experiments whose
promotion requires evidence or unavailable deployment data. Status is updated
only after the corresponding tests and reports exist. A runnable experiment is
not a production-approved model.

## 1. Objective and non-negotiable properties

Improve detection and measurement while preserving the public contract:

```python
source[span.start:span.end] == span.text
```

The [first principles](02-first-principles.md) imply the following acceptance
rules. Tests must challenge the implementation rather than mirror its code.

| Principle | Required evidence |
| --- | --- |
| The source is the editable object | Accents, combining marks, CJK, emoji, invisible characters, repeated values, and nonzero window offsets all slice the original string. |
| An unprocessed tail is not a clean result | Token-budget coverage is checked; every window advances and covers the source, or the operation raises a source-free error. |
| A miss can cross the trust boundary | Measure actual masking intervals and high-severity complete containment, before and after merge. |
| Independent identifiers remain independent | A losing bridge span cannot suppress a disjoint winning candidate. Results remain deterministic under input permutation. |
| A score is not a guarantee | Calibrate on development data and inspect negatives; no invented probabilities for grammar matches. |
| Measurement has a definition | Corpus materialization, annotation policy, type crosswalk, scorer, and selection are versioned together. |
| Secrets are irreversible | No credential value enters the vault, including mixed-type overlap and structured-mapping cases. |
| Cloud detection copies the original | Modal uses synthetic/public evaluation inputs and explicit private SDK invocation; local presets do not acquire an automatic cloud fallback. |

## 2. Implementation sequence and status

| ID | Priority | Deliverable | Evidence | Acceptance | Status |
| --- | --- | --- | --- | --- | --- |
| IMP-01 | P0 | Versioned SPY materialization and annotation-policy audit | E1, E2; R1, R4 | Correctly typed synthetic IDs; legacy reports retained; new protocol identified in every report; author-only versus broad discovery called out. | Implemented; versioned reruns and protocol tests |
| IMP-02 | P0 | Overlap resolution that retains disjoint winners | E3; F1, F4 | Bridge counterexample fixed; all permutation tests agree; output is disjoint; severity policy and complexity remain explicit. | Implemented; permutation/bridge tests passed on Modal |
| IMP-03 | P0 | Token-aware bounded inference | E4; R7; M3 | Special-token overhead included; Unicode/dense-token tail controls pass; no silent truncation; original offsets preserved. | Implemented for HF and GLiNER2; legacy adapters unadmitted |
| IMP-04 | P0 | Containment, character damage, and coverage diagnostics | R3, R6; current reports | Exact typed scores retained; untyped character containment and negative masking are separate; no denominator silently excludes unsupported requested types. | Implemented; interval, repetition, negative-damage tests and Modal reports |
| IMP-05 | P1 | New model experiments with pinned adapters | M1, M2, M3 | Actual inference on Modal; decoder/offset contract validated; outputs and failures recorded; compatible candidates only. | Implemented; experiments completed, quality failures retained |
| IMP-06 | P1 | First-principles regression suite and Modal validation | F1–F10; R8, R13 | Offline suite, model runtime tests, site build/checks, and browser checks run on Modal; machine-readable evidence retained. | Verified: 204 passed, one optional test skipped on Modal |
| IMP-07 | P1 | Documentation and site evidence pages | R1–R13 | Research, plan, limitations, benchmark interpretation, and links render correctly; site claims match checked-in evidence. | Updated; site build/browser checks passed; final evidence recheck below |
| IMP-08 | P2 | Domain adaptation learning curve | R2, R4 | Only after permissioned annotated data and a sealed split exist; test 100/500/1,000 training examples with fixed dev/test and repeated seeds. | Conditional: data not yet available |
| IMP-09 | P2 | Edge compression and model-specific optimized runtimes | M5, M8 | Float/quantized boundary and containment parity assessed; report latency, memory, and accuracy jointly. | Conditional experiment |
| IMP-10 | P2 | Conversation policy, tool necessity, and surrogate utility | R7, R9–R12 | Separate policy and task-utility datasets; deterministic restoration tests; secrets remain irreversible; no anonymity claim. | Conditional research stage |

IMP-01 through IMP-07 are the immediate implementation scope. Later stages
are genuine outstanding work, not implied completed features. They must not be
marked complete merely because the library tests pass.

## 3. Repair the benchmark contract first — IMP-01

### Change

Preserve historical SPY generation as an explicitly named legacy protocol.
Introduce a new version that selects a declared generator from a seeded local
random source and uses government-ID-shaped values only when the declared
public label is `GOV_ID`. Do not pass RIPE network handles, IBANs, or cards off
as government IDs. Record generator/version, Faker version, seed, source policy,
and selection digest. Avoid process-global random-state interference.

Maintain a written crosswalk from native corpus labels to public types. A
generic source identifier does not establish its subtype. For ambiguous
original records, exclude the unsupported type from a clearly labeled
common-support diagnostic, retain its unsupported count, and do not call the
result full-taxonomy recall. A separate synthetic control can establish the
government-ID mechanics without claiming it represents deployment data.

### Tests and evidence

- Generated ID examples conform to the declared category and reproduce under
  the same version/seed; the generator does not mutate global Faker randomness.
- Legacy protocol reproduces legacy inputs; changing a generation protocol
  changes report identity. Old report bytes are retained.
- Reports state that SPY annotations are author-associated. A broad-discovery
  model's extra spans are not automatically adjudicated as hallucinations.
- The model ranking is rerun after protocol changes, with all models using
  identical source/gold selections. No prediction-driven rewriting of gold.

## 4. Preserve independently useful spans — IMP-02

Write [ADR 0005](adr/0005-overlap-and-coverage.md) before changing overlap policy.
Within an overlap component, select the highest-priority candidate, remove only
candidates that directly conflict with that winner, then continue resolving the
remaining intervals. Deterministic ranking stays based on taxonomy severity,
preferred detector lane, length, score, and stable lexical tie-breakers.

The bridge example must keep `GOV_ID[5:9]` and `EMAIL[18:30]`. Test chains,
nested ranges, equal ranks, equal offsets, duplicates, and shuffled detector
order. Benchmark ordinary disjoint input separately from adversarial dense
overlaps so the documented complexity matches the actual algorithm.

This does not prove every discarded candidate is harmless. Keep conflict
diagnostics and compare pre-merge versus post-merge containment. Do not silently
turn a heterogeneous interval union into an invented public PII type.

## 5. Prove model input coverage — IMP-03

Character count is a resource bound, not a token budget. Derive windows from
the actual tokenizer and effective model context, including special tokens and
schema overhead where applicable. Preserve character offsets on each original
window. Verify that the final model input fits; split further or raise rather
than letting a library truncate invisibly.

The optional legacy GLiNER and ModelScope adapters remain unadmitted for
token-coverage claims. Their tokenizer/configuration paths still require
model-specific validation before that guarantee can be extended to them. For GLiNER2/2.5, account for schema tokens and use the supported
long-input path or checked chunks. A longer-context model does not remove
boundary-crossing tests. Very long mentions may require an explicit unsupported
input error if no valid window can contain both endpoints.

Adversarial controls put synthetic identifiers after dense Unicode prefixes,
inside overlap regions, and at every window edge. The tests must use fake
tokenizers with more tokens than characters, not just ASCII examples for which
the old heuristic happened to work.

## 6. Measure the product outcome — IMP-04

Keep exact typed precision/recall/F1/F2. Add:

- **Untyped complete containment:** a gold range is protected only if the union
  of masking intervals covers all its characters, regardless of predicted type.
- **Sensitive-character recall:** covered gold characters divided by gold
  characters, computed using interval unions so overlaps are counted once.
- **Masking precision:** masked gold characters divided by all masked
  characters, under the declared annotation policy. Interpret incomplete gold
  as a limitation, not proof of low utility.
- **PII-free document false-positive rate:** fraction of audited negative
  documents that lose any characters, plus masked-character fraction.
- **Repeated-identifier complete coverage:** all mentions must be removed; a
  single missed recurrence fails that identifier's outcome.
- **Operational completeness:** failures, invalid offsets, unsupported labels,
  over-budget inputs, and incomplete documents are explicit outcomes. Failed
  inputs cannot be removed from the success denominator.

Compare exact typed and containment metrics side by side. A broad OPF
`account_number` can contain sensitive digits while lacking enough evidence to
choose `GOV_ID` versus `PAYMENT`. Do not force a false public type to make a
model fit. Native-label experiments remain labeled as such until a sound
public taxonomy decision exists.

## 7. Run a staged model tournament — IMP-05

### First batch

Retain `rules`, current `en-closed`, and current `multi-open` controls. Add the
compatible Horizon small encoder first, then GLiNER2.5 boundary extraction.
Add OPF using its native decoder and a reviewed taxonomy crosswalk, or retain
it as an explicit native-label experiment where the public mapping is
ambiguous. Do not reuse generic token aggregation merely because it runs.

Every adapter must pin weights, tokenizer, model code if required, decoder,
label schema, and runtime package versions. Review only the necessary pinned
code; do not execute floating remote helper modules. Test adapters alone and
in combination with rules so the rule lane cannot hide a nonfunctional model.

Liquid and Protegrity remain conditional on license/code/access review;
ShinrAI weights require access review. Kiji and OpenMed require their proper
sequence decoders. Their existence does not block the first compatible batch.

### Data and selection

Use the audited SPY legal/medical tracks, finance, structured forms, hard
negatives, and a versioned first-principles challenge set. Declare training
overlap for every model and dataset. Public benchmarks screen candidates;
they do not constitute a sealed deployment freeze.

The private target set remains unavailable. Proposed collection must include
the deployment's actual languages, domains, and document lengths, with two
annotators and adjudication of disputed policy/boundary cases. Group splits by
template family, original document, and conversation. Near-duplicates and
translations cannot cross splits. Do not treat absent private data as consent
to send production PII to an annotation service.

### Modal execution

- Use the existing private SDK model class and persistent public-weight cache.
  Run CPU controls and GPU candidates explicitly; record actual GPU hardware.
- Run one representative load/inference preflight before larger evaluations.
  Bound document count, container count, startup time, and invocation time.
- Keep single-request warm p50/p95 separate from batch throughput, cold start,
  model loading, and network time. Record memory and failures where available.
- Use unique report identity and a run-completion manifest so stale files from
  a previous run cannot be mistaken for new evidence.
- Measure model-only and rules-plus-model outcomes. If quality does not improve,
  retain the result rather than changing gold or suppressing failed slices.

The first batch is exploratory and bounded. Wider GPU spending and production
promotion require explicit budgets and risk floors; no paper's hardware price
or throughput becomes our service SLO.

## 8. First-principles testing on Modal — IMP-06

Run the full repository test suite in a clean Modal CPU environment, including
the actual wheel/source layout and site tools. Run actual model inference in
the GPU runtime. Keep offline deterministic tests separate from statistical
model quality: both must pass their own criteria.

| Layer | Required challenge | Evidence to retain |
| --- | --- | --- |
| Contract | Unicode, repeated text, shifted chunks, invalid model surfaces | Test results and dropped/error counts |
| Merge | Disjoint survivors behind a losing bridge, nested secrets, permutations | Regression tests; severity-policy ADR |
| Tokenization | Dense Unicode and schema overhead, identifier beyond first context | Checked windows; no hidden truncation |
| Mask/restore | Round trip for reversible spans and mappings; secret absent from vault | Property-like deterministic fixtures |
| Metrics | Partial masking, wrong labels, duplicate gold, negative-only inputs | Hand-calculated expected counts |
| Models | Rule-disabled smoke plus fixed matched-corpus comparison | Pinned model/runtime/selection reports |
| Website | Build, internal links, research/plan navigation, responsive browser smoke | Modal logs, test report, screenshots |

Instruction-like text and Unicode evasion are adversarial controls. No test may
assert that a detector is safe merely because its confidence is high.

## 9. Documentation and site — IMP-07

Publish this plan, the research update, the model manifest, and the overlap ADR
through the static site's existing documentation routes. Update the docs index,
research/catalog pointers, evaluation guide, and historical assessment erratum.
Explain the SPY qualification near the older scores. Preserve the historical
reports and source contract. Site claims must identify an experiment as an
experiment, and a model-card number as external evidence.

The local build and the Modal build must pass link checks. Browser checks must
confirm the new pages are reachable and readable, including a narrow viewport.
Updating repository site content is separate from publishing the production
GitHub Pages deployment; record which actually occurred.

## 10. Promotion criteria and later experiments

Keep the existing requirement of zero observed high-severity containment
failures on a human-audited sealed freeze. Precision, per-type recall, latency,
negative damage, and supported-language floors remain **UNCONFIRMED** until the
deployment owner chooses them on development data and commits them before the
sealed run. The earlier CLI example of 0.90 recall is not a universal product
requirement.

Use paired document-level bootstrap intervals for candidate differences on
larger runs, clustering by conversation/template where required. Do not claim
significance from 50 prefix-selected records. Zero observed errors on a finite
freeze is not zero future risk.

Only after those steps should IMP-08 test domain adaptation with a fixed
train/dev/test split, repeated seeds, category-balanced sampling, hard negatives,
and replay data to detect forgetting. Human-reviewed corrections stay separate
from model-generated labels. Learning-curve sizes are experimental proposals,
not guaranteed crossover points.

IMP-09 evaluates quantization against the identical float decoder. IMP-10
requires an explicit tool-necessity policy, repeated-mention conversation gold,
and downstream task checks for surrogates. Do not invent cryptography, replace
secret irreversibility, or equate retained task utility with anonymity.

## 11. Completion record

Implemented on 5 November 2026. IMP-01 through IMP-07 now have code and
validation evidence. IMP-08 through IMP-10 remain conditional, and no model
has been promoted to a production default.

### First-principles implementation and verification

- SPY materialization uses local random state, seeded generator selection,
  government-ID-shaped synthetic values, and an explicit protocol. Legacy
  reports remain unchanged. Both SPY domains were rerun on identical input/gold
  selections for every candidate.
- Direct-conflict merge retains independent winners, with deterministic
  tie-breaking and O(n log n) interval indexing. The bridge, dense-overlap,
  secret-vault, source-offset, and permutation controls passed.
- HF and GLiNER2 check actual encoded windows, including special tokens and
  schema. Tests cover more tokens than characters, dense Unicode tails, and
  impossible schema/character budgets. All six model lanes also exercised
  actual Modal inference on fixed Unicode, repeated-value, long-prefix,
  mask/restore, and rule-disabled controls.
- Reports retain exact typed scores, complete and character containment,
  unmapped counts, within-document repeated-value coverage, and pre-policy
  candidate coverage. The final gated confirmation also records source and
  masked-character fractions. Hand-calculated controls prove that a wrong
  label can still mask a value, that a missed recurrence fails all-mentions
  coverage, and that audited-negative damage has an explicit denominator.
- New experiments pin Horizon Small, GLiNER2.5 boundary extraction, and OPF's
  official native Viterbi runtime. OPF retains its native labels and rejects
  changed decoded text or invalid claimed surfaces. Public typed SDK presets
  do not silently acquire OPF's coarse label meanings.

The [full Modal verification](eval/validation/2026-11-05-final/validation.json)
completed with **204 passed, 1 skipped, 0 failed** in the test suite. The one
skip is the optional HF demo-browser test in a CPU environment without model
weights; real T4 inference is recorded separately below. The run also built
and installed the wheel, proved the installed-package source/mask/restore and
no-torch rules contract, regenerated the site data/icons/social images, built
and checked all 30 HTML pages, audited completed model reports, and exercised
Chromium at 1440 px and 390 px.

Evidence: [JUnit](eval/validation/2026-11-05-final/junit.xml),
[desktop screenshot](eval/validation/2026-11-05-final/site-1440.png),
[mobile screenshot](eval/validation/2026-11-05-final/site-390.png), and
[Modal run](https://modal.com/apps/raphaelmansuy/main/ap-R2chwxXg095SO9Iua4E1xa).
The JSON retains source-file hashes, the wheel hash, dependency versions, and
step exit codes. After this completion record is rendered, a separate
`--site-only` Modal run rechecks the final pages, report links, and both browser
viewports. Its narrower scope is labeled in its saved evidence.

### Matched public experiments

Six lanes completed all four corpus runs: **24 corpus/preset reports**, plus
one explicit-gate confirmation. Rules use four CPU cores; models use an NVIDIA
T4. Every main run has one matched selection hash across its six reports.
Every learned typed lane also has a full **model-only ablation on the same
inputs** inside its JSON. The fixed inference smoke requires model detections
with the rule detector disabled.

These are bounded public prefix samples, not a sealed deployment freeze.
SPY uses `government-id-v2` and author-associated gold. Nemotron is an
in-domain control for ModernBERT. Training overlap is not excluded for the
other public checkpoints. No significance or whole-language guarantee follows
from these samples. Tables below use the report's `all` slice; the Nemotron
minority slices are shown separately. F1 is exact and typed; containment is
untyped complete-span coverage. A dash for OPF means no typed projection was
made, not a score of zero. p95 covers warm locate calls, including tokenization
and merging, and excludes loading, transport, and scoring.

**Two main experiments failed the invalid-offset gate:** GLiNER2.5 on legal
and GLiNER2-PII on medical each returned one rejected span. Their run manifests
are `quality-gates-failed`, and their CLI commands exited nonzero. Other rows
passing the permissive integration policy are not production approvals.

#### SPY legal

50 documents and 254 gold spans in `all`; 50 unique inputs evaluated across all requested slices. [Completion manifest](eval/modal/spy-legal-50-0e100240/run.json); [Modal run](https://modal.com/apps/raphaelmansuy/main/ap-gzZgM8cimRJlKQ7i0FJDMq).

| Preset / JSON | Exact P | Exact R | Exact F1 | Model-only F1 | Containment | High-severity misses | Invalid offsets | Warm p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [rules](eval/modal/spy-legal-50-0e100240/spy-legal__rules-50.json) | 0.295 | 0.311 | 0.303 | — | 0.343 | 30 | 0 | 6.3 ms |
| [en-closed](eval/modal/spy-legal-50-0e100240/spy-legal__en-closed-50.json) | 0.187 | 0.728 | 0.297 | 0.268 | 0.752 | 6 | 0 | 98.7 ms |
| [multi-open](eval/modal/spy-legal-50-0e100240/spy-legal__multi-open-50.json) | 0.311 | 0.819 | 0.451 | 0.445 | 0.945 | 3 | 0 | 170.2 ms |
| [multi-encoder](eval/modal/spy-legal-50-0e100240/spy-legal__multi-encoder-50.json) | 0.319 | 0.933 | 0.476 | 0.478 | 0.972 | 0 | 0 | 88.3 ms |
| [multi-boundary](eval/modal/spy-legal-50-0e100240/spy-legal__multi-boundary-50.json) | 0.264 | 0.689 | 0.382 | 0.377 | 0.858 | 11 | 1 | 169.2 ms |
| [opf-native](eval/modal/spy-legal-50-0e100240/spy-legal__opf-native-50.json) | — | — | — | — | 0.921 | 0 | 0 | 1491.0 ms |

#### SPY medical

50 documents and 311 gold spans in `all`; 50 unique inputs evaluated across all requested slices. [Completion manifest](eval/modal/spy-medical-50-e42b5910/run.json); [Modal run](https://modal.com/apps/raphaelmansuy/main/ap-FnnjXPWHnoNWiXE85S3QBX).

| Preset / JSON | Exact P | Exact R | Exact F1 | Model-only F1 | Containment | High-severity misses | Invalid offsets | Warm p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [rules](eval/modal/spy-medical-50-e42b5910/spy-medical__rules-50.json) | 0.359 | 0.283 | 0.317 | — | 0.302 | 41 | 0 | 5.5 ms |
| [en-closed](eval/modal/spy-medical-50-e42b5910/spy-medical__en-closed-50.json) | 0.218 | 0.707 | 0.333 | 0.314 | 0.727 | 6 | 0 | 95.3 ms |
| [multi-open](eval/modal/spy-medical-50-e42b5910/spy-medical__multi-open-50.json) | 0.380 | 0.781 | 0.511 | 0.511 | 0.865 | 23 | 1 | 174.5 ms |
| [multi-encoder](eval/modal/spy-medical-50-e42b5910/spy-medical__multi-encoder-50.json) | 0.366 | 0.887 | 0.518 | 0.530 | 0.942 | 10 | 0 | 66.0 ms |
| [multi-boundary](eval/modal/spy-medical-50-e42b5910/spy-medical__multi-boundary-50.json) | 0.303 | 0.659 | 0.415 | 0.418 | 0.772 | 25 | 0 | 161.8 ms |
| [opf-native](eval/modal/spy-medical-50-e42b5910/spy-medical__opf-native-50.json) | — | — | — | — | 0.875 | 2 | 0 | 1493.5 ms |

#### Gretel finance

50 documents and 151 gold spans in `all`; 50 unique inputs evaluated across all requested slices. [Completion manifest](eval/modal/gretel-finance-en-50-86e9aa29/run.json); [Modal run](https://modal.com/apps/raphaelmansuy/main/ap-Za7CZsGRqYFz2HUbmyxLQj).

| Preset / JSON | Exact P | Exact R | Exact F1 | Model-only F1 | Containment | High-severity misses | Invalid offsets | Warm p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [rules](eval/modal/gretel-finance-en-50-86e9aa29/gretel-finance-en__rules-50.json) | 0.340 | 0.119 | 0.176 | — | 0.126 | 10 | 0 | 6.2 ms |
| [en-closed](eval/modal/gretel-finance-en-50-86e9aa29/gretel-finance-en__en-closed-50.json) | 0.127 | 0.318 | 0.181 | 0.155 | 0.331 | 5 | 0 | 59.6 ms |
| [multi-open](eval/modal/gretel-finance-en-50-86e9aa29/gretel-finance-en__multi-open-50.json) | 0.458 | 0.821 | 0.588 | 0.610 | 0.901 | 0 | 0 | 137.1 ms |
| [multi-encoder](eval/modal/gretel-finance-en-50-86e9aa29/gretel-finance-en__multi-encoder-50.json) | 0.551 | 0.781 | 0.647 | 0.643 | 0.834 | 4 | 0 | 45.2 ms |
| [multi-boundary](eval/modal/gretel-finance-en-50-86e9aa29/gretel-finance-en__multi-boundary-50.json) | 0.471 | 0.854 | 0.607 | 0.635 | 0.914 | 5 | 0 | 136.4 ms |
| [opf-native](eval/modal/gretel-finance-en-50-86e9aa29/gretel-finance-en__opf-native-50.json) | — | — | — | — | 0.728 | 1 | 0 | 1460.1 ms |

#### Nemotron

25 documents and 53 gold spans in `all`; 75 unique inputs evaluated across all requested slices. [Completion manifest](eval/modal/nemotron-pii-25-a9d52b9f/run.json); [Modal run](https://modal.com/apps/raphaelmansuy/main/ap-jOiSwxLQUtgdN22zprvjVo).

| Preset / JSON | Exact P | Exact R | Exact F1 | Model-only F1 | Containment | High-severity misses | Invalid offsets | Warm p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [rules](eval/modal/nemotron-pii-25-a9d52b9f/nemotron-pii__rules-25.json) | 0.400 | 0.151 | 0.219 | — | 0.151 | 11 | 0 | 4.2 ms |
| [en-closed](eval/modal/nemotron-pii-25-a9d52b9f/nemotron-pii__en-closed-25.json) | 0.680 | 0.962 | 0.797 | 0.879 | 0.962 | 2 | 0 | 36.5 ms |
| [multi-open](eval/modal/nemotron-pii-25-a9d52b9f/nemotron-pii__multi-open-25.json) | 0.494 | 0.736 | 0.591 | 0.629 | 0.906 | 2 | 0 | 54.9 ms |
| [multi-encoder](eval/modal/nemotron-pii-25-a9d52b9f/nemotron-pii__multi-encoder-25.json) | 0.581 | 0.811 | 0.677 | 0.748 | 0.962 | 2 | 0 | 29.5 ms |
| [multi-boundary](eval/modal/nemotron-pii-25-a9d52b9f/nemotron-pii__multi-boundary-25.json) | 0.500 | 0.566 | 0.531 | 0.580 | 0.774 | 9 | 0 | 53.4 ms |
| [opf-native](eval/modal/nemotron-pii-25-a9d52b9f/nemotron-pii__opf-native-25.json) | — | — | — | — | 0.943 | 2 | 0 | 1307.5 ms |

`--limit 25` means a prefix per slice, not only 25 model calls. Each cell below is **exact recall / high-severity misses** on 25 documents. OPF cells show **untyped containment / misses**. Slice memberships overlap and must not be summed.

| Preset | US | International | Structured | Unstructured |
| --- | ---: | ---: | ---: | ---: |
| rules | 0.151 / 11 | 0.218 / 5 | 0.155 / 8 | 0.200 / 9 |
| en-closed | 0.962 / 2 | 1.000 / 0 | 0.972 / 2 | 0.980 / 0 |
| multi-open | 0.736 / 2 | 0.600 / 0 | 0.634 / 4 | 0.640 / 0 |
| multi-encoder | 0.811 / 2 | 0.636 / 0 | 0.732 / 2 | 0.740 / 0 |
| multi-boundary | 0.566 / 9 | 0.473 / 4 | 0.634 / 7 | 0.500 / 5 |
| opf-native | 0.943 / 2 | 0.982 / 0 | 0.944 / 2 | 0.940 / 0 |

### Decisions from these results

Horizon Small is the strongest exact-recall candidate on these legal and
medical prefixes, but it still misses ten high-severity spans on medical and
four on finance. Its legal exact precision is only 0.319 under SPY's
annotation policy. GLiNER2-PII has higher recall than Horizon on finance and
zero measured high-severity misses there. ModernBERT leads exact recall on
its in-domain Nemotron control. There is no single production winner.

The [explicit-gate Horizon confirmation](eval/modal/spy-legal-50-835c8e36/spy-legal__multi-encoder-50.json)
passed **0.90 exact recall and zero high-severity misses on this legal slice**:
recall 0.933, complete-span containment 0.972, character recall 0.990, and
masked-character fraction 0.0753. That run also passed the image's Parquet
import preflight and `pip check`.
[Modal run](https://modal.com/apps/raphaelmansuy/main/ap-Y8LAVQOPxyY0aiyQy2Fv8V).
These are scoped experimental gates. Negative damage floors, deployment
precision, language coverage, private data, and the sealed freeze remain
unconfirmed. Zero-gold document counts in public corpora do not establish an
audited negative set.

Rules do not improve every exact-F1 result. The model-only ablations preserve
that evidence: for example, GLiNER2.5 finance F1 is higher alone than with
rules. Rule preference and overlap decisions can trade typed correctness for
masking coverage. Before/after diagnostics also show remaining policy losses,
so the bridge fix must not be described as a proof that merging cannot leak.

OPF's native containment and high-severity outcomes are useful independent
measurements, but its roughly 1.3–1.5 second p95 in these runs is much slower
than the small encoders. No batch-throughput number or model-card partial F1
is substituted for those measured request latencies. Peak memory and target
edge-device performance were not measured.

### Reproduction, failures, and publication scope

```bash
# Repeat each of the four matched runs; limit is per slice.
.venv/bin/modal run modal/models.py --corpus spy-legal --limit 50 --gpu T4 \
  --presets rules,en-closed,multi-open,multi-encoder,multi-boundary,opf-native
.venv/bin/modal run modal/models.py --corpus spy-medical --limit 50 --gpu T4 \
  --presets rules,en-closed,multi-open,multi-encoder,multi-boundary,opf-native
.venv/bin/modal run modal/models.py --corpus gretel-finance-en --limit 50 --gpu T4 \
  --presets rules,en-closed,multi-open,multi-encoder,multi-boundary,opf-native
.venv/bin/modal run modal/models.py --corpus nemotron-pii --limit 25 --gpu T4 \
  --presets rules,en-closed,multi-open,multi-encoder,multi-boundary,opf-native
.venv/bin/modal run modal/models.py --corpus spy-legal --limit 50 --gpu T4 \
  --presets multi-encoder --min-recall 0.90 --max-leaks 0
.venv/bin/modal run modal/validate.py
.venv/bin/modal run modal/validate.py --site-only
.venv/bin/python modal/check_evidence.py
```

The initial OPF attempt used the Transformers root conversion with the native
runtime and failed. The corrected adapter explicitly loads `original/` at the
same pinned model revision. The initial finance image also failed because
Arrow 26 required NumPy 2 at import while the runtime used NumPy 1.26.4; the
image now pins compatible Arrow 20 and checks imports and dependencies before
allocating a model. Failed manifests remain
[here](eval/modal/spy-legal-50-e29f487e/run.json) and
[here](eval/modal/gretel-finance-en-50-a1c0ba80/run.json). They are not treated as
completed benchmark results. Historical legacy reports are unchanged.

The optional legacy GLiNER and ModelScope weights, gated/restricted models,
custom CRF/ONNX candidates, domain adaptation, quantization, and surrogate/tool
utility studies remain unvalidated or conditional as stated above. First-
principles tests establish the challenged invariants, not complete PII recall
or a mathematical proof of system safety.

Repository documentation and all new site routes/evidence assets are updated.
The static site is built and browser-tested. The existing Pages workflow
publishes changes after merge to `main`; its
[deployment runs](https://github.com/raphaelmansuy/edgepii/actions/workflows/site.yml)
record the actual publication status. No package release, production default
change, fine-tuning run, or public inference endpoint is implied.
