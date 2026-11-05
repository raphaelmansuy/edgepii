# Improvement research after 0.4.0: 5 November 2026

This research combines primary-source review with **16 completed single-model
Modal evaluations and four paired experiments**. The cutoff is 5 November,
not the end of November. The results change the earlier brainstorming:
compact checkpoints are useful controls, but neither new float model earns a
general replacement, and the released int4 artifact does not preserve coverage.

The work adds repository-only research adapters, reproducible experiments, and
tests. The published [0.4.0 package](19-release-0.4.0.md) and public presets retain
their release behavior. No training, calibrated router, streaming service,
production promotion, or new package publication occurred in this research.

## Evidence and experiment design

- [Six-model artifact manifest](research/compact-model-manifest-2026-11-05.json):
  exact revisions, current license declarations, file sizes/LFS hashes, and
  hashes of inspected cards, configurations, notices, and license files.
- [Recomputed result summary](research/compact-results-summary-2026-11-05.json):
  all report hashes, matched selection digests, paired coverage, and support
  counts. `scripts/audit_compact_research.py` checks this evidence and recomputes
  paired summaries from saved source-free case outcomes.
- Three public prefixes: 50 legal, 50 medical, and 50 finance records; 254, 311,
  and 151 in-scope gold spans. CPU and paired studies reuse these inputs.
  These are exploratory prefixes, not a new sealed deployment test.
- All new comparisons retain **native labels**, original source, and union
  containment. They do not claim public typed F1. No rules or confusable folding
  are added. The Horizon control therefore differs from the typed
  `multi-encoder` system in the [previous results](18-protection-and-model-results.md).
- SPY retains `government-id-v2`, seed 42, and author-associated annotation.
  Its omitted identifiers and broader native vocabularies mean character
  masking precision cannot by itself measure unwanted masking or task utility.
- Float experiments use the pinned Torch/Transformers runtime on a T4. The
  portable quantized control uses ONNX Runtime 1.23.2 on four Modal CPU threads.
  Warm p95 measures complete `locate` calls, including tokenization, windows,
  decoding, and source-offset handling; loading and downstream task work are excluded.
- GPU memory is peak Torch allocated memory during evaluation. CPU RSS is
  process-lifetime peak, including imports and loading. This shared research
  image imports heavyweight libraries; its RSS is not a lean edge-runtime footprint.

Native categories may include types absent from a public gold policy. A zero
high-severity count covers only that sample's gold and supported measurement;
it does not establish that a model recognizes every credential or identifier.

## Literature that changes the next engineering decisions

| Primary source | Finding relevant to EdgePII | Engineering consequence |
| --- | --- | --- |
| [Unified Labels, 15 Oct 2026](https://arxiv.org/html/2610.22597v1) | Consistent category definitions and labeled negative traffic are central to its compact detector. Its operating-point analysis distinguishes real false positives from all flags on unlabeled traffic. | Audit category meaning and model-specific crosswalks; calibrate on adjudicated negatives. A quiet detector is not automatically precise. |
| [RedactionBench, 17 Jun 2026](https://arxiv.org/html/2606.18782v1) | Separates mandatory/contextual redactions and formatting connectors, with limited agreement on contextual choices. | Preserve our exact metric, then add policy-aware diagnostics and explicit connector rules as separate experiments. Ambiguous policy labels need adjudication. |
| [RedacBench, 2 Mar 2026](https://arxiv.org/html/2603.20208v1) | Evaluates removed sensitive propositions and retained useful information. Its limitations discuss evaluator hallucinations and contamination. | Add downstream task success and inference-attack tests. LLM review drafts need checks; an attack model failing to recover a value is empirical evidence, not a privacy guarantee. |
| [LeakageBench, 2 Sep 2026](https://arxiv.org/html/2609.02207v1) | Separates page-level exposure, schema support, detection, OCR, and spatial alignment. This is an image benchmark. | Add document/session leakage to text evaluation. An OCR adapter would additionally need original-image box coverage; text-span correctness cannot certify pixel redaction. |
| [SAE suppression diagnosis, 3 Nov 2026](https://arxiv.org/html/2611.04782v1) | Of 36 intervention configurations, 17 pass a logprob-only criterion but one passes the authors' combined criteria and matched controls. It studies LLM memorization, not span NER. | Retain outcome tests and independent controls. Changes in model confidence or internal activations do not establish removal of source values. SAE steering is outside the current implementation track. |

[REDACT](https://github.com/guneeshvats/REDACT-PII-Benchmark) remains a useful
multilingual/disclosure-form expansion. Its released protocol and label schema
must stay separate from SPY's author policy and our broad discovery task.
Its small obfuscated slice should not become a strong robustness claim.

## Artifact review and admission

| Candidate | Verified artifact facts | Decision for this research |
| --- | --- | --- |
| [Masker Mini](https://huggingface.co/divergentlabs/masker-mini) | 35,399,857 parameters, Apache-2.0 declaration; 49 BIOES labels across 12 entity categories. Released float weights and int4 ONNX graph. | Run float and int4 as native-label experiments. It has no general SECRET category. Retain NOTICE/attribution requirements when distributing artifacts. |
| [Ettin 32M](https://huggingface.co/kalyan-ks/ettin-32m-nemotron-pii) | 32,072,171 parameters, MIT metadata; ModernBERT classifier trained on Nemotron, with a different native inventory. | Run independent legal/medical/finance controls. Its Nemotron card score cannot establish out-of-domain performance. |
| [Conway MLX](https://huggingface.co/ConwayResearch/pii-30M-mlx-4bit-v1.0/blob/8c1d53a68ef27cbac0f1d56e4847fb9184f82b5d/LICENSE) and [Core ML](https://huggingface.co/ConwayResearch/pii-30M-coreml-ane-v1.0/blob/6f2c61bba6f94f6fa689055114ad10fa33b26ed4/LICENSE) | Both pinned current cards and primary LICENSE files declare CC-BY-NC-4.0; separate Apache files are also present. | Correct the earlier brainstorming based on a cached Apache card. Exclude both from the unrestricted commercial shortlist. Apple runtime performance is unmeasured. |
| [GLiNER Streaming PII](https://huggingface.co/knowledgator/gliner-stream-pii-v1.0) | Apache-2.0 metadata; native streaming architecture, cached sessions, and recomputation. | Conditional conversation experiment; no streaming inference measurement in this study. A buffering/commit policy must precede upstream emission. |
| [Blackbar Nano](https://huggingface.co/safetype/blackbar-nano) | Apache-2.0 metadata; custom span head and split ONNX graphs. | Adapter-review control, not a generic token-classification drop-in. Not measured here. |

The Masker card's pretrained-student initialization is a useful distillation
ablation for future training. Its published quantization agreement is measured
on its own validation distribution; our parity experiment below tests a
different question on these public prefixes.

### Decoder admission matters

Masker emits B/I/E/S/O tags. The adapter explicitly performs argmax BIOES
decoding, including closing E/S tokens, recording how orphan I/E tags start
spans, and preserving offsets through checked windows. It executes no remote
model code. Special tokens, Unicode combining marks, malformed ranges, tag
changes, and native labels have independent regression examples.

Ettin and Horizon use the checked Transformers pipeline with native labels.
Their labels are not silently coerced into EdgePII's taxonomy. PII-Tracer
retains its previously reviewed, hash-verified native Viterbi runtime.

## Actual T4 measurements

Each row uses 50 records. Containment requires every character of a gold span
to be covered by the native range union. Misses below are high-severity
containment failures, not total false negatives.

| Corpus | Native model | Containment | Misses | Warm p95 |
| --- | --- | ---: | ---: | ---: |
| Legal | Masker Mini | 0.622 | 0 | 28.9 ms |
| Legal | Ettin 32M | 0.815 | 6 | 58.4 ms |
| Legal | Horizon Small | 0.972 | 0 | 60.4 ms |
| Legal | PII-Tracer | 0.992 | 0 | 191.3 ms |
| Medical | Masker Mini | 0.650 | 0 | 23.8 ms |
| Medical | Ettin 32M | 0.836 | 15 | 54.1 ms |
| Medical | Horizon Small | 0.981 | 0 | 60.7 ms |
| Medical | PII-Tracer | 0.965 | 0 | 192.8 ms |
| Finance | Masker Mini | 0.616 | 4 | 19.2 ms |
| Finance | Ettin 32M | 0.662 | 6 | 28.6 ms |
| Finance | Horizon Small | 0.775 | 4 | 36.7 ms |
| Finance | PII-Tracer | 0.974 | 0 | 101.1 ms |

Completion manifests and all four reports per corpus:
[legal](eval/modal/spy-legal-50-5fdf7be4/run.json),
[medical](eval/modal/spy-medical-50-55290bac/run.json),
[finance](eval/modal/gretel-finance-en-50-9418dddc/run.json).
Modal runs: [legal](https://modal.com/apps/raphaelmansuy/main/ap-sUIhN6RZ4fFDvzB0ZuNenr),
[medical](https://modal.com/apps/raphaelmansuy/main/ap-nqf96nPBg5MaX7aJImubbP),
[finance](https://modal.com/apps/raphaelmansuy/main/ap-hUcGjfKXtAY5j2Z3UYLYOX).

**Interpretation:** Masker is faster but loses substantial full-span coverage
under this gold policy. Its segmented address/name inventory also differs
from full-address/person gold; character recall and examples must accompany
containment. Ettin provides no general quality improvement over the Horizon
control here. Native Horizon is a different system from the projected, folded,
rules-assisted preset; these results do not erase that system's earlier misses.

## CPU and int4 results

Same medical prefix, four CPU threads:

| Native model | Containment | Misses | Warm p95 | Process peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Masker float | 0.650 | 0 | 152.7 ms | 5038 MiB |
| Masker int4 ONNX | 0.643 | 0 | 165.6 ms | 4780 MiB |
| Ettin float | 0.839 | 14 | 283.9 ms | 5072 MiB |
| Horizon float | 0.981 | 0 | 457.8 ms | 5508 MiB |

[Completion manifest](eval/modal/spy-medical-50-733d5cc0/run.json),
[Modal run](https://modal.com/apps/raphaelmansuy/main/ap-089K7wLQm4UYBujltC3dOS).
These RSS values include the research harness. GPU and CPU Ettin outputs also
differ slightly; identical weights do not establish cross-runtime span parity.

The released Masker files are 70,811,538 bytes for stored float weights and
22,344,556 bytes for the int4 ONNX graph. That smaller file was about **8.5%
slower** at medical warm p95 here. Torch inference uses fp32 parameters after
loading the stored float artifact; file size and live memory are distinct.

Paired CPU studies use the same tokenizer, window policy, and BIOES decoder:

| Corpus | Float contained | Int4 contained | Float / int4 high-severity misses | Exact range parity, documents | Exact native-span parity, documents |
| --- | ---: | ---: | ---: | ---: | ---: |
| Medical, 311 gold | 202 | 200 | 0 / 0 | 16 / 50 | 8 / 50 |
| Finance, 151 gold | 93 | 91 | 4 / 5 | 32 / 50 | 29 / 50 |

Reports: [medical](eval/paired/spy-medical-50-quantized-f59f4ca4.json),
[finance](eval/paired/gretel-finance-en-50-quantized-449da1bc.json).
Modal: [medical](https://modal.com/apps/raphaelmansuy/main/ap-53DJaZP6y3bWlihQStqf3C),
[finance](https://modal.com/apps/raphaelmansuy/main/ap-4Gxgef8NzD7w2kT2NFAROA).
Exact range parity compares canonical masked interval unions; native-span parity
also requires labels and boundaries to agree. These are not token-agreement metrics.

### Precision metadata correction

Direct Modal probes of [GPU parameters](research/compact-runtime-precision-2026-11-05.json)
and [CPU parameters](research/compact-runtime-precision-cpu-2026-11-05.json)
verified the actual loaded precision under the same Torch 2.8.0 / Transformers
5.22.1 pins: **Ettin uses bfloat16; Horizon and Masker use float32**, on both devices.
The original Ettin reports' `native_backend` string ending in `fp32` was an
unverified annotation and is incorrect. Historical reports retain their bytes;
their measured containment/latency values are unchanged. The adapter now records
the loaded dtype instead of assuming it. The tables' float references mean
non-int4 inference, not a uniform precision across model families.
An Ettin fp32 ablation has not been run; the observed rows compare the loader
behavior of the released candidates and cannot isolate architecture from precision.
Probe runs: [GPU](https://modal.com/apps/raphaelmansuy/main/ap-RBV4gSkSmhf2LcoBDf3bK7),
[CPU](https://modal.com/apps/raphaelmansuy/main/ap-aZMRbVMM9Fz2xNMi5Y3Kn0).

**Decision:** retain int4 as an experiment. It adds a finance high-severity miss,
so smaller storage does not justify promoting it as an equivalent runtime.
See [ONNX Runtime's quantization guidance](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)
for its emphasis on debugging accuracy changes.

## Do complementary errors justify an ensemble?

Paired experiments compute each detector on the same original document and
score the actual interval union. They can credit complementary partial ranges
that jointly cover a gold span even when neither alone does. Tests include
that counterexample. Saved case outcomes contain coverage flags and counts,
without source strings, document IDs, or extracted values.

| Corpus / combination | Single-model contained spans | Union contained | Union high-severity misses | Additional masked characters |
| --- | ---: | ---: | ---: | ---: |
| Medical: Horizon + Masker | 305 / 202 | 305 | 0 | 647 over Horizon |
| Medical: Horizon + Tracer | 305 / 300 | 307 | 0 | 1549 over Horizon |
| Finance: Horizon + Masker | 117 / 93 | 128 | 2 | 602 over Horizon |
| Finance: Horizon + Tracer | 117 / 147 | 147 | 0 | 1280 over Tracer |

Reports: [medical](eval/paired/spy-medical-50-complementarity-2f132a4b.json),
[finance](eval/paired/gretel-finance-en-50-complementarity-bcd3f281.json).
Modal: [medical](https://modal.com/apps/raphaelmansuy/main/ap-eR2LH8FmXVq9BBuX7EEIen),
[finance](https://modal.com/apps/raphaelmansuy/main/ap-JrtfGIkVfwGehNFJ11leUF).

**Decision:** test a domain-aware policy only after independent validation.
Horizon + Masker recovers two finance high-severity misses, but adds no medical
containment. Adding Horizon to Tracer adds no finance complete-span containment.
Extra masked characters can include both omitted PII and unwanted damage;
the table does not adjudicate utility. No adaptive router or routed latency
was measured. A lack of detected spans cannot by itself justify skipping a verifier.

### A taxonomy discrepancy worth investigating first

On identical medical inputs, native Horizon has no high-severity misses while
the earlier typed system has ten. The paired support audit records four
single-span supports of gold `GOV_ID` under native `MEDICAL_ID`, which the
current global crosswalk leaves unmapped. Counts describe supporting predictions,
not necessarily unique gold entities.

That demonstrates a concrete vocabulary/policy gap, but it does not explain
all ten differences. Native versus typed systems also differ in normalization,
trimming, filtering, and overlap policy. Do not map every medical identifier
to a government ID to improve this sample. A stage-by-stage counterfactual
audit and model-specific category definitions should precede a public mapping change.
Strict protection already rejects nonzero unmapped diagnostics by default.

## Prioritized improvement plan

| Priority | Research-backed work | Required evidence before promotion |
| --- | --- | --- |
| P0 | Gate the actual emitted protection path; audit unknown labels, normalization, trimming, and arbitration separately. Add a private case viewer. | Replay fixed failures, preserve original offsets and secret exclusion, distinguish incomplete inference, and trace every coverage change to a stage. |
| P1 | Build an adjudicated target-domain development set and sealed test, with audited negatives and uncommon types. | Split by conversation/template/translation lineage before tuning; document policy, contamination checks, per-slice counts, and document/session leakage. |
| P2 | Compare always-on and domain-selected two-model policies using the demonstrated complementary cases. | Fixed risk/utility/latency budgets; random audits for shared misses; measured end-to-end routing performance on a new test. |
| P3 | Test conversation state and buffered streaming against repeated, reformatted, corrected, and split identifiers. | No previously emitted sensitive prefix; role/turn offsets, tenant/session isolation, bounded cache lifetime, and actual released-text tests. |
| P4 | Train a pretrained compact student using reviewed teacher drafts and hard negatives; compare learning curves and seeds. | Teacher adds coverage on independent examples; labels satisfy category definitions; sealed replay detects forgetting and rare-type regression. |
| P5 | Revisit ONNX/quantization in a lean standalone runtime, then actual target devices. | No added high-severity misses under the declared policy, per-type boundary checks, model/runtime hashes, measured p95/RSS, and device-specific results. |

P0/P1 are the next implementation priority. P2 has exploratory supporting
evidence on finance, not a universal ensemble result. P3–P5 remain conditional
experiments; no deployment-domain data or human adjudication was invented.
Downstream usefulness and contextual re-identification require separate outcome
tests, with empirical attacks distinguished from formal privacy guarantees.

## Reproduction and first-principles checks

```bash
.venv/bin/python scripts/research_snapshot.py --out /tmp/compact-models-new-snapshot.json
.venv/bin/modal run modal/models.py --corpus spy-medical --limit 50 --gpu T4 \
  --presets masker-mini-native,ettin-native,horizon-native,tracer-native
.venv/bin/modal run modal/models.py --corpus spy-medical --limit 50 --gpu cpu \
  --presets masker-mini-native,masker-int4-native,ettin-native,horizon-native
.venv/bin/modal run modal/models.py --corpus spy-medical --limit 50 --gpu T4 --paired
.venv/bin/modal run modal/models.py --corpus gretel-finance-en --limit 50 --gpu cpu --paired --quantized
.venv/bin/modal run modal/models.py --inspect-only --gpu T4 \
  --presets ettin-native,horizon-native,masker-mini-native --out /tmp/compact-runtime-probe.json
.venv/bin/python scripts/audit_compact_research.py
.venv/bin/modal run modal/validate.py
```

The artifact collector records a fresh snapshot, so future upstream changes
must not silently replace this dated manifest. Experiment constants pin the
revisions measured here. Native models remain evaluation-only SDK rejections.
The single-model run manifests retain integration gates; those permissive gates
do not establish a zero-leak quality pass.

[Initial paired launch failures](research/compact-launch-attempts-2026-11-05.json)
are retained separately. They failed before inference because of unsupported
function options or inconsistent remote import/resource construction. The
corrected paired worker runs through the established Modal Model class.
Those failed starts are not counted among the completed experiments.

## Validation record

The [final full Modal verification](eval/validation/2026-11-05-compact-final/validation.json)
passed **257 tests, with one optional weight-dependent demo test skipped**.
It built and exercised the installed wheel, audited all completed model reports,
recomputed the paired evidence, rebuilt the site, and checked desktop/mobile
browsers. [JUnit](eval/validation/2026-11-05-compact-final/junit.xml),
[Modal run](https://modal.com/apps/raphaelmansuy/main/ap-AC3Y0UUGm1Woox8tUTIgCL).
The [earlier full run](eval/validation/2026-11-05-compact-research/validation.json)
is retained with its own source hashes.
The new regression examples cover BIOES boundaries, Unicode/source offsets,
invalid token schemas, complementary partial masks, and range-versus-label parity.
The [final documentation and audit check](eval/validation/2026-11-05-compact-site-final/validation.json)
passed **17 tests with no skips** on Modal, after the precision correction and
publication evidence were added.
