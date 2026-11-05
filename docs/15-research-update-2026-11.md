# Research and model update: 5 November 2026

Status: verified research inputs for the [implementation plan](16-grounded-improvement-plan.md).
The cutoff is **5 November 2026**, not the end of November. This is a targeted
review of sources relevant to EdgePII's contract, not an exhaustive leaderboard.
Paper results, publisher claims, local reproductions, and proposed experiments
are distinguished below. New models have not earned production status by
appearing in this document.

## 1. Correct the measurement before replacing the model

The earlier [Modal reports](14-assessment-2026-11.md#measured-modal-result) remain
historical measurements of the code and inputs recorded in those files:

| Preset | Exact precision | Exact recall | Exact F1 | Reported high-severity leaks | Warm p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rules, CPU | 0.281 | 0.283 | 0.282 | 37 | 8.1 ms |
| ModernBERT, T4 | 0.163 | 0.606 | 0.258 | 37 | 96.6 ms |
| GLiNER2-PII, T4 | 0.262 | 0.768 | 0.391 | 28 | 292.1 ms |

These are 50 selected documents and 254 gold spans, not independent evidence of
deployment quality. The research audit found two important qualifications.

**E1 — the generic-ID materializer is inconsistent with our public type.**
In the earlier [corpora.py](../src/edgepii/eval/corpora.py), `materialize_spy` called
`pool[0]`. For `ID_NUM`, this is `fake.ripe_id()`. Faker 40.44.0 with seed 42
generates values such as `ORG-VRPO1-RIPE`. Both SPY registry entries map
`ID_NUM` to `GOV_ID`. All 37 high-severity gold spans in this legal sample are
in that bucket. They are not validated government-ID examples. Therefore,
"37 government-ID leaks" is not a supported interpretation of the reports.
Changing the generator requires a new derived-data version and new scores;
historical reports must not be rewritten.

**E2 — SPY's definition differs from broad identifier discovery.** The
[SPY paper, Appendix D and limitations](https://aclanthology.org/2025.naacl-srw.23.pdf)
labels author-associated information and deliberately includes other people's
identifiers as distractors. EdgePII's public default is broad span discovery.
Some apparent false positives can therefore be policy disagreements. Keep an
author-specific SPY track and a separate human-audited broad-discovery track.
Do not relabel the test merely to make a preferred model win.

Two other local checks identify engineering work independently of any paper:

- **E3 — transitive overlap can discard an unrelated accepted span.** Injecting
  `PERSON[0:20]`, `GOV_ID[5:9]`, and `EMAIL[18:30]` into the earlier `merge_spans`
  returned only `GOV_ID[5:9]`. The email does not overlap that winner. A losing
  broad span connected them into one group. This is a structural counterexample,
  not a measured frequency in production.
- **E4 — character windows do not prove full model coverage.** The earlier HF
  adapter used 75% of the position limit as a character budget; GLiNER adapters
  used 8,000 characters. Neither establishes a token limit for arbitrary Unicode,
  dense identifiers, or label prompts. Correct returned offsets do not establish
  that the tail was processed.

The repairs and measured outcomes are tracked in the
[implementation completion record](16-grounded-improvement-plan.md#11-completion-record).
These counterexamples describe the starting implementation.

## 2. Research that changes the engineering decisions

All quantitative results here belong to the cited authors' protocols. They are
not EdgePII scores. A preprint is identified as such rather than treated as
peer-reviewed production evidence.

| ID | Primary source and version available by cutoff | Relevant result | Consequence for EdgePII |
| --- | --- | --- | --- |
| R1 | [Broad and Efficient PII Detection with Unified Labels, v1, 15 Oct 2026](https://arxiv.org/html/2610.22597v1), Cisco AI Defense preprint | A 141M encoder trained on consistently relabeled data achieves strong recall at low false-positive operating points. The work distinguishes label names from contextual annotation definitions. | Write category definitions, annotate hard negatives, and audit corpus mappings before increasing model size. No released checkpoint was verified in this review; use the method, not an invented model ID. |
| R2 | [Strong Multilingual Privacy Tagging at Encoder Speed, v3, 13 Oct 2026](https://arxiv.org/html/2609.38630v3), preprint | Adding mapped human annotations improves the authors' human-set redaction F1 by ten points relative to frontier-generated labels alone. | Human-adjudicated evaluation and training examples matter. The authors release recipes and code, **not weights or training data**; this is a training reference, not a downloadable candidate. |
| R3 | [Protegrity-PII Technical Report, v2, 28 Oct 2026](https://arxiv.org/html/2610.30518v2), vendor preprint | Reports typed precision 0.902 and recall 0.910 on its PII-SCOPE set; distinguishes typed and untyped matching. | Evaluate fine-grained models under a symmetric taxonomy crosswalk. Its own benchmark and batch-throughput claims do not transfer to EdgePII's request latency. Model licensing limits its production candidacy. |
| R4 | [OpenAI Privacy Filter cross-domain evaluation, v2, 6 Aug 2026](https://arxiv.org/html/2608.02616v2), independent preprint | The revised study covers 32 benchmarks and 14 languages. Domain-adapted XLM-R crosses its zero-shot baseline with hundreds to roughly a thousand labeled examples, depending on domain. | Run a learning curve if audited errors persist. This is evidence for testing adaptation, not a guarantee that 500 EdgePII examples will suffice. Do not mix the earlier 42-benchmark v1 with v2. |
| R5 | [GLiNER2-PII technical report, v1, 11 May 2026](https://arxiv.org/html/2605.09973v1) | Schema-conditioned extraction supports fine-grained PII labels; the paper's SPY average F1 is 0.471. | Retain the existing PII-specialized baseline. Test canonical model-specific labels instead of sending every alias in a shared cross-model taxonomy. The current card reports 0.477 under its table; preserve the discrepancy. |
| R6 | [REDACT, v1, 18 Jun 2026](https://arxiv.org/html/2606.19881v1), preprint | Controlled variation includes 25 languages, disclosure form, sensitivity, length, density, and code-switching. On its 1,000-record experiment OPF's partial F1 is 0.512 while exact F1 is 0.171. | Add language and disclosure-form slices. Retain exact typed scoring, but also measure character containment and masking damage. Never compare partial-F1 claims directly to EdgePII exact F1. |
| R7 | [PII-TRACE, v1](https://arxiv.org/html/2609.22200v1), preprint | Studies repeated identifiers across multi-turn conversations. Its 0.6B PII-Tracer and benchmark are promised upon publication. | Add repeated-mention and cross-turn coverage tests. No public PII-Tracer checkpoint was verified; it cannot be placed in a runnable manifest yet. |
| R8 | [Mind the Gap, v1, 3 Sep 2026](https://arxiv.org/html/2609.03464v1), preprint | Rules, an encoder, and a generative extractor fail differently under distribution shift. This is a robustness study, not a ranking of the newest models. | Add OCR, informal formatting, obfuscation, and domain-shift controls. Measure complementary misses before considering an ensemble. |
| R9 | [ToolMinimize, v1, 25 Aug 2026](https://arxiv.org/html/2608.24957v1), authors' accepted PST version | Tool arguments can disclose more information than tool functionality needs; syntax-valid arguments do not prove end-task success. | Extend existing mapping support with explicit field-level policy and task-validity tests. A span detector alone cannot decide which city a weather tool needs. |
| R10 | [SurrogateShield, v1, 28 Jun 2026](https://arxiv.org/html/2606.29567v1), preprint | Reports utility gains for type-consistent replacement under a limited synthetic/adversarial evaluation. | Treat surrogate replacement as a separately evaluated strategy. BERTScore and a small attack trial are not proof of anonymity or task preservation. Secrets stay irreversible. |
| R11 | [Veil-Then-Reveal, v2, 23 Oct 2026](https://arxiv.org/abs/2610.22800v2), preprint | Separates detection, protection of detected values, and round-trip restoration; proposes format-preserving mechanisms. | Measure each stage independently. Do not import new cryptography or call reversible substitution anonymization. |
| R12 | [PromptPET, v1, 3 Jul 2026](https://arxiv.org/html/2607.02932v1), preprint | Studies privacy versus task utility for redaction, abstraction, replacement, and noising. | Keep semantic inference risk outside the span recall claim; evaluate useful task outputs separately. |
| R13 | [JevBreak, v1, 2 Nov 2026](https://arxiv.org/abs/2611.03759v1), adjacent decision-model preprint | Constrained answers and high confidence do not establish resistance to adversarial evidence. Its experiments concern decision models, not EdgePII span NER. | Add instruction-like adversarial text to the detector test suite. This is a test hypothesis, not a claimed attack success rate for our models. |

## 3. Model candidates and actual integration requirements

The [machine-readable manifest](research/model-manifest-2026-11-05.json) records
14 inspected repositories, exact available revisions, API metadata, and hashes
of fetched cards/configurations/license files. No weights were downloaded for
this review. Repository creation and commit dates are not assumed to be model
release dates. A metadata license tag is not a substitute for the governing
license file. HTTP 401/404 and missing pins are retained rather than hidden.

| ID | Candidate and source | Why consider it | Integration and admission decision |
| --- | --- | --- | --- |
| M1 | [Horizon-Labs/pii-redactor-small](https://huggingface.co/Horizon-Labs/pii-redactor-small), plus its `pii-redactor-base` control | Recent multilingual mmBERT token classifiers; small has about 141M parameters, 29 entity types, Apache-2.0, and published ONNX artifacts. Both inspected snapshots were updated 31 Oct. | First new closed-lane experiment. Use tokenizer offsets and an explicit label map. Its card's label-agnostic redaction results are not exact typed F1. Avoid executing downloaded helper code when the existing adapter can do the work. |
| M2 | [openai/privacy-filter](https://huggingface.co/openai/privacy-filter), [official runtime](https://github.com/openai/privacy-filter) | Apache-2.0; single-pass BIOES classification, eight native categories, advertised 128k context. | Use the native constrained decoder and verify source round trips. The existing generic `simple` aggregation is not evidence of decoder equivalence. Broad `account_number` and generic dates cannot be silently mapped into narrower public types. Evaluate native containment separately where necessary. |
| M3 | [fastino/gliner2.5-multi-v1](https://huggingface.co/fastino/gliner2.5-multi-v1), with `gliner2.5-small-v1` as a cost control | Newer boundary extraction architecture, Apache-2.0, variable span lengths within its encoded window. | Load through `AutoExtractor` / `BoundaryExtractor`, not the legacy `GLiNER2` class. It is a general extractor, not automatically a better PII fine-tune. Its long-document helpers still have chunk limitations. |
| M4 | [LiquidAI/LFM2.5-Encoder-350M-PII-Detector](https://huggingface.co/LiquidAI/LFM2.5-Encoder-350M-PII-Detector) | Roughly 355M parameters; 40 PII types, 16 languages on the card; token classification. | Conditional experiment after reviewing its custom license and pinned custom code. The card's preferred results use hybrid decoding and partial-F1; isolate model-only and helper-assisted performance. Do not enable floating `trust_remote_code=True`. |
| M5 | [knowledgator/gliner-pii-edge-v1.0](https://huggingface.co/knowledgator/gliner-pii-edge-v1.0) | Apache-2.0 and published quantized ONNX variants; useful CPU/edge control. | Benchmark the complete tokenizer/decoder/artifact combination against its float reference. Quantized model names do not establish span parity. |
| M6 | [OpenMed/privacy-filter-nemotron](https://huggingface.co/OpenMed/privacy-filter-nemotron) | Apache-2.0; replaces OPF's coarse categories with 55 Nemotron categories. | Dedicated BIOES decoding and taxonomy crosswalk required. The card uses 10,000 Nemotron test rows for validation; do not treat that same population as an untouched promotion test. External domains matter more than another in-domain win. |
| M7 | [DataikuNLP/kiji-pii-model](https://huggingface.co/DataikuNLP/kiji-pii-model) | Apache-2.0, six languages, 26 PII categories, CRF decoder. | A useful constrained-decoding control, but the custom MLP/CRF head does not load correctly as a generic `AutoModelForTokenClassification`. Lower priority than compatible token classifiers. |
| M8 | [nationaldesignstudio/rampart](https://huggingface.co/nationaldesignstudio/rampart) | Approximately 18.5M parameters; 14.7 MB released ONNX artifact; seven Latin-script languages; CC BY 4.0. | Edge-efficiency control after attribution and artifact review. The published system combines learned entities with deterministic recognizers; evaluate both the model and full system rather than crediting wrapper rules to the model. |
| M9 | [Protegrity/protegrity-pii](https://huggingface.co/Protegrity/protegrity-pii) | Released 27 Oct according to its card; XLM-R-based spans over 69 types. | Research comparison only under the published research/non-commercial terms. Gated weights and custom license exclude it from an unrestricted commercial default. Its PII-SCOPE dataset is distinct from the older similarly named training-data-leakage benchmark. |
| M10 | [innovius/shinrai-pii-m-v1.3](https://huggingface.co/innovius/shinrai-pii-m-v1.3) | Multi-head multilingual model with local ONNX serving and replacement-related attributes. | Conditional license/access review. The public card gives revenue-dependent terms; v1.5 is managed API, not the released local weights. Anonymous API retrieval returned 401, so no revision was invented. |
| M11 | [fastino/GLiNER2-Guardrails-PII-Multi](https://huggingface.co/fastino/GLiNER2-Guardrails-PII-Multi) | Joint moderation and PII extraction, Apache-2.0. | Optional system experiment only if moderation is a product requirement. A joint task is not proof of improved PII recall; preserve the PII-only baseline. |

Keep the current pinned ModernBERT and GLiNER2-PII presets as controls. Do not
replace them merely because a newer base architecture exists. The Cisco and
Graehl papers provide methods; PII-Tracer remains availability-dependent.
Generative extractors, cloud-only detectors, and document decision models do
not replace the exact-source span interface without an explicit contract change.

### Highest-value adaptation details

The [OpenAI output schema](https://github.com/openai/privacy-filter/blob/main/OUTPUT_SCHEMAS.md)
includes original span text and a decode-mismatch indication. A mismatch must
not be repaired by searching for a repeated value. The
[official evaluation guidance](https://github.com/openai/privacy-filter/blob/main/EVAL_AND_OUTPUT_MODES.md)
distinguishes typed from untyped evaluation when label spaces differ.

The [GLiNER2.5 card's long-document section](https://huggingface.co/fastino/gliner2.5-multi-v1#long-documents)
explicitly states that a bounded extraction call truncates, and that chunked
helpers do not stitch mentions whose endpoints never share a chunk. "Unlimited
span length" means within the encoded window, not unlimited document coverage.

The Liquid card's copy-paste usage names a different repository spelling from
its canonical `350M` model URL. Use the inspected canonical ID and pinned
artifacts; validate examples instead of copying them untested.

## 4. Decisions this evidence supports

1. Repair evaluation semantics and overlap behavior before promoting any model.
2. Add a compatible multilingual encoder, a native-decoding OPF experiment, and
   a boundary-extractor experiment; compare them on the same audited inputs.
3. Count both exact typed correctness and the characters actually removed.
   Report unsupported categories and negative-text damage, not just recall.
4. Prove token-window coverage, including CJK and dense punctuation. Treat
   incomplete processing as an error rather than a clean scan.
5. Reserve adaptation, compression, conversation policy, and surrogates for
   separate measured stages. Preserve local execution and irreversible secrets.

The [grounded plan](16-grounded-improvement-plan.md) turns these decisions into
implementation tasks, first-principles tests, Modal evidence, and site changes.
