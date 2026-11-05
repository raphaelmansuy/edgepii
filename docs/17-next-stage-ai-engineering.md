# Next-stage AI engineering: coverage, calibration, and model selection

Reviewed **5 November 2026**, after the [implemented first-stage plan](16-grounded-improvement-plan.md).
This is a prioritized proposal. New candidate metadata and source files were
inspected; no new weights were downloaded, custom model code executed, or
inference results measured for this review. Existing Modal results remain the
measurement baseline. The [candidate manifest](research/model-manifest-phase2-2026-11-05.json)
pins the inspected artifacts, and the [baseline reanalysis](research/phase2-baseline-analysis-2026-11-05.json)
records report hashes and the arithmetic behind the recommendations.

The next priority is **preserving coverage through policy, then evaluating
additional models against adjudicated errors**. The current evidence does not
support choosing a universal replacement or promoting a new default.

## 1. What the completed experiments tell us

| Observed result | What it establishes | Next experiment |
| --- | --- | --- |
| ModernBERT legal: candidate high-severity misses 4, final misses 6; medical: 5 to 6. `min_score` was unset. | Conflict resolution can remove protection that valid mapped candidates supplied. These three added misses are downstream of detection. | Preserve eligible candidate coverage in a separate protection plan; measure additional masking damage. |
| Rules reduce exact F1 in 9 of 16 matched typed comparisons, improve it in 6, and tie in 1. | Combining rules and models is a policy decision with costs. It is not automatically better on this metric. | Compare model-only, rules-only, and combined systems, including complete containment and negative damage. |
| ModernBERT Nemotron exact F1: 0.879 alone, 0.797 with rules. All seven non-secret types present in that `all` slice have no exact false negatives. | Added predictions can damage precision even when recall remains high. The slice is in-domain and only 25 documents. | Inspect unwanted recognitions and boundary/type disagreements before adding another encoder. |
| Horizon Small exact recall: 0.933 legal, 0.887 medical, 0.781 finance. GLiNER2-PII finance: 0.821, with zero measured high-severity misses there. | Domain differences matter. Aggregate results do not identify whether two detectors miss the same examples. | Collect paired per-case coverage outcomes before designing routing or an ensemble. |
| GLiNER2.5 legal and GLiNER2-PII medical each return one rejected span. | A successful model smoke does not establish corpus-wide source-offset correctness. | Reproduce the rejected surfaces and test the correct decoder/offset convention; retain the existing rejection until fixed. |

These observations use the `all` prefix slice of each existing report. They
are descriptive, not independent trials or significance tests. SPY's
author-associated policy also differs from broad discovery: an extra predicted
name is not automatically an unwanted redaction. No gold is changed to improve
a candidate's score.

## 2. First change: distinguish entity description from protection

The existing `Span` contract remains useful: a typed, disjoint result on the
original source. Selecting one description for an overlap does not establish
that the discarded characters may safely leave the boundary.

Propose an **opt-in `ProtectionPlan`**, separate from `locate()` and the
existing typed merger. It consumes validated candidates after explicit type
and score eligibility. It records protection intervals and provenance without
inventing a public PII type for a heterogeneous union.

Required invariants for this experiment:

1. Every character covered by an eligible candidate is covered by the plan.
   Overlap arbitration cannot reduce that coverage.
2. Intervals index the original string. Construction never searches for a
   repeated value to repair an invalid offset.
3. Every character covered by an eligible `SECRET` candidate is irreversible.
   No overlap with another type may put any credential fragment in the vault.
4. Protection segments are disjoint. Partitioning at candidate boundaries can
   preserve active-type provenance and secret handling; restoration must be
   tested across those segments.
5. Invalid offsets, incomplete inference, and unsupported requested categories
   are explicit diagnostic outcomes. They cannot be silently reported as a
   fully processed clean document.

Begin with counterfactual evaluation and an opt-in API. Union masking can
remove more non-PII text, especially with broad false-positive candidates. It
must meet a measured negative-damage budget before becoming a default. The
invariant concerns supplied eligible candidates; it cannot protect an
identifier missed by every detector. Keep the typed result and exact scorer
unchanged so the trade is visible.

Acceptance includes nested SECRET/GOV_ID/PERSON ranges, losing bridges,
adjacent intervals, duplicate and permuted inputs, repeated placeholders,
Unicode, and structured mappings. Measure actual masked output, vault content,
and restoration, not just interval geometry.

Also test **country-specific identifier recognizers** behind explicit
application profiles. The current rule detector has no GOV_ID recognizer,
while the corrected SPY protocol deliberately generates US SSN-shaped IDs.
A constrained US profile is a useful low-cost control before fine-tuning a
larger model for those misses. Use contextual cues and published structural
rules, and test collisions with order IDs and unrelated numeric strings.
[SSA's structural exclusions](https://www.ssa.gov/employer/randomizationfaqs.html)
provide negative controls; passing a format check does not establish that a
number was issued or belongs to anyone. Keep the country scope explicit,
measure recall lost by requiring cues, and do not turn this into an automatic
worldwide GOV_ID rule or assign a probability to a grammar match.

## 3. Model candidates worth testing next

Availability correction: the earlier review missed the public
[Perplexity PII-Tracer checkpoint](https://huggingface.co/perplexity-ai/PII-Tracer).
Its official model repository and the
[PII-TRACE dataset](https://huggingface.co/datasets/perplexity-ai/PII-TRACE)
are now verified in the manifest. The paper's release-promise wording did not
establish artifact availability. This correction does not add a measured
EdgePII result for that model.

The verified Hub release is a **500-conversation English subset**, currently
exposed as a `train` split, with 450 positive and 50 empty-control conversations
according to its card. It is not the paper's entire multilingual benchmark.
Its training/evaluation lineage must be checked before ranking PII-Tracer on
it. Current gold spans occur in user messages; the artifact does not establish
assistant-message detection quality. Preserve `(turn, role, start, end)` and
original message text when implementing the conversation adapter.

| Priority | Candidate | Why it adds information | Adapter and admission requirements |
| --- | --- | --- | --- |
| A | [Horizon-Labs/pii-redactor-base](https://huggingface.co/Horizon-Labs/pii-redactor-base), Apache-2.0, about 308M parameters | Same-family capacity control against the already tested 141M Small. | Reuse checked token windows and the explicit label crosswalk. The publisher's own table has cases where Small is better; size is not a promotion criterion. |
| A | [perplexity-ai/PII-Tracer](https://huggingface.co/perplexity-ai/PII-Tracer), MIT, about 596M parameters | Conversation-oriented encoder with nine categories, constrained BIOES decoding, and a separate sensitivity head. | Review and pin its custom code. Preserve bidirectional Qwen3 attention and native Viterbi decoding. Its helper truncates at 4,096 tokens, so use checked windows and verify original-source spans. Evaluate native containment where coarse categories lack a sound public projection. |
| A, edge track | [crp4222/privaite-pii-minilm](https://huggingface.co/crp4222/privaite-pii-minilm), BSD-3-Clause, about 117M parameters | A compact multilingual control with released PyTorch, ONNX, int8, and Core ML artifacts. | Native `CONTACT` mixes email, phone, URLs, and usernames; `FINANCIAL` also spans several public meanings. Start with native containment or a reviewed common-support diagnostic. Do not map these labels blindly into EMAIL/PAYMENT. Verify float/quantized boundaries and coverage. |
| B, only for streaming requirements | [knowledgator/gliner-stream-pii-v1.0](https://huggingface.co/knowledgator/gliner-stream-pii-v1.0), Apache-2.0 | Adds causal cached streaming and session recomputation, a distinct capability from the current stateless API. | Requires GLiNER's streaming architecture and session-state tests. Recomputing later cannot recover private text already sent upstream; a committed-prefix/buffering policy is part of the experiment. |

The manifest contains full revisions; the first three are respectively
`ef0eff8e63c1711ec0c997c5ca9ea3b78a068684`,
`d25c16f2e57e321f6d2527715c01df9112f956f5`, and
`e5f6a01d465c9a2489a74a95ff1151359b759213`.

PII-Tracer's sensitivity output is advisory and must not suppress span
detection. Its implementation derives span scores from transformed logits;
those are not established probabilities of complete protection. Its official
vLLM/GGUF/MLX repositories are alternate packagings, not additional independent
models. The MLX card explicitly requires a loader implementation that is not
included. Start with the reference runtime before testing alternate engines.

### Models to keep conditional

- [Dataiku Kiji](https://huggingface.co/DataikuNLP/kiji-pii-model) remains a
  useful CRF control with a custom head/decoder. Liquid's PII encoder also
  remains conditional on custom-code and license review. Neither is a generic
  pipeline drop-in merely because it carries a token-classification tag.
- [Stirling-Minimo v0.2](https://huggingface.co/VidaiUK/stirling-minimo-pii-10m-v02)
  is an interesting 10M ONNX efficiency reference, but the published
  CC-BY-NC-4.0 terms do not make it an unrestricted commercial default. Its
  card separates checkpoint behavior from the served system and uses masking
  F2. Do not substitute those claims for our exact typed scores or latency.
- [ScienceSoft's encoder](https://huggingface.co/ScienceSoft/scnsoft-pii-encoder)
  has proprietary terms that do not grant production use of the released
  weights. Its disclosure of seed variance and benchmark reuse is useful
  evaluation practice, not a deployment license.
- [Deerpark's edge checkpoint](https://huggingface.co/Deerpark/pii-tagger-edge)
  is gated. Protegrity and ShinrAI retain the access/license qualifications in
  the first review. A public card or permissive metadata field is not enough
  to admit a model or all its dependencies.

## 4. Apply AI engineering principles to this closed task

[Hamel Husain's error-analysis guidance](https://hamel.dev/blog/posts/field-guide/)
supports reading concrete failures before choosing tools. The first artifact
should be a private or synthetic/public **case viewer**: original text, gold,
raw valid candidates, selected spans, protection intervals, and a reviewer
reason. Real source values stay in the approved review boundary and out of
`docs/eval/`, telemetry, and public pages. The current aggregate reports cannot
support document-level disagreement analysis by themselves.

[Anthropic's January 2026 evaluation guidance](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)
distinguishes outcomes, graders, regression checks, and capability tests.
For EdgePII the deterministic outcome is the actual protected string and its
source ranges. Human reviewers adjudicate ambiguous annotation policy; an LLM
does not decide exact-span correctness. New multilingual/OCR/conversation cases
are capability tests; verified failure fixes join the regression suite.

Operationalize those principles in this order:

1. **Separate error causes.** Label detection misses, boundary shifts,
   unsupported categories, normalization effects, decoder/offset failures,
   and protection-policy losses separately. Audit label granularity too: a
   city fragment, complete address, generic date, and date of birth are not
   interchangeable annotations.
2. **Create a policy-aligned development set.** Use adjudicated examples from
   actual target languages, domains, lengths, and structured formats. Include
   audited negatives. Keep SPY author-associated and broad-discovery tracks
   separate. Public or model-generated drafts require human verification.
   Permissioned deployment data and domain-owner review remain dependencies.
3. **Make splits before optimization.** Group by document, template family,
   conversation, and translation lineage. Keep a sealed test distinct from
   the already inspected public prefixes. Never fine-tune on these reported
   test examples and continue calling them untouched evaluation.
4. **Optimize operating points, not one aggregate F1.** Choose per-model/type
   thresholds on development data under a high-severity containment constraint,
   precision/negative-damage budgets, and latency/memory limits. Model scores
   require calibration checks; rule scores remain unscored. Freeze criteria
   before the sealed run and inspect every required minority slice.
5. **Test complementary errors before routing.** Persist privacy-appropriate
   paired coverage outcomes, then measure which misses a second detector
   recovers and how much text it damages. Use trusted application domain
   metadata for initial routing trials. Low confidence alone is not a reliable
   escalation trigger because a confident miss emits no span at all.
6. **Adapt only after error taxonomy and clean splits exist.** Test learning
   curves such as 100/500/1,000 adjudicated training examples, repeated seeds,
   rare-category balance, hard negatives, and replay against forgetting. These
   are proposed experiment sizes, not known crossover points. Distill only
   after a teacher demonstrates additional coverage on independent examples.

Use paired document-level intervals for model differences on larger samples,
clustering related templates/conversations. Keep a small random audit alongside
disagreement sampling: agreement does not reveal shared blind spots. Zero
observed leaks on a small prefix is not a bound on all future traffic.

## 5. Concrete implementation order and evidence gates

| Work item | Deliverable | Exit condition | Status |
| --- | --- | --- | --- |
| NEXT-01 | Case-level diagnostics, invalid-span reproductions, and opt-in coverage-preserving protection plan | No protection loss among eligible candidates; no secret material in vault; masked-output and negative-damage tests pass. | Proposed; highest priority |
| NEXT-02 | Adjudicated development set, explicit category definitions, sealed group split | Annotation disputes resolved; overlap/contamination checks; target-channel negative and rare-category coverage. | Requires approved data and review |
| NEXT-03 | Horizon Base, native PII-Tracer, and native/common-support MiniLM adapters | Pinned reference decoders; Unicode/window/surface checks; model-only and rules-plus-model runs; unsupported types remain visible. | Proposed; metadata verified only |
| NEXT-04 | Paired candidate comparison and calibrated policy | Candidate selected under committed safety, utility, latency, and memory criteria; results retained when gates fail. | Depends on NEXT-01–03 |
| NEXT-05 | Targeted adaptation and optional distillation | Fixed splits, repeated seeds, retained teacher comparisons, no regression on independent replay. | Conditional experiment |
| NEXT-06 | CPU/ONNX/Core ML optimization and optional streaming | Float/runtime/quantized parity by type and language; actual target-device latency/RSS; streaming committed-prefix and session isolation tests if needed. | Conditional on product requirement |

For NEXT-03, reuse Modal's private SDK workers and cached public weights.
Preflight one synthetic document with each adapter before a bounded matched
tournament. Record model/code/tokenizer/decoder pins, input selection hashes,
failures, cold load, warm p50/p95, throughput, peak GPU memory, CPU RSS, and
cost on the same hardware and workload. Include model-only and full-system
measurements. Existing permissive integration gates do not become promotion
gates just because an experiment runs successfully.

Expand evaluation with long and structured inputs, OCR-like damage,
non-Latin/combining-mark scripts, secrets in code/configuration, and repeated
mentions across conversations. Check licenses and annotation policy for
PII-TRACE and other added corpora before ingesting them. The detector's own
training distribution is an in-domain control, not its decisive ranking set.

Modal CPU results do not establish Apple Neural Engine, browser, or mobile
performance. Local-first inference remains the default boundary; any cloud
second stage stays explicit and opt-in. Model-output logs and session caches
must not become an accidental store of private source values.

**Recommended next pull request:** NEXT-01, followed by the three NEXT-03
reference adapters and a matched experiment once its evaluation policy is
declared. Keep model default changes, fine-tuning, and edge-runtime promotion
separate so each decision has reviewable evidence.

## Documentation verification

This research update's site route, corrected availability note, and pinned
manifest passed the [Modal site verification](eval/validation/2026-11-05-next-stage-site/validation.json):
17 tests passed, no skips, including desktop/mobile browser checks and the
complete static-site build. This validates the documentation integration;
it is not an inference test of the newly proposed models.
