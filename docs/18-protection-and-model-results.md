# Protection and model results: 5 November 2026

This implements the core protection work and reference-model experiments from
the [next-stage roadmap](17-next-stage-ai-engineering.md). Protection, country
profiles, and Horizon Base remain opt-in; PII-Tracer and MiniLM are native-label
Modal experiments. The existing typed span contract and defaults are unchanged.

The protection APIs and fixes are included in **edgepii 0.4.0**. Upgrade with
`pip install --upgrade edgepii==0.4.0`. See the [release guide](19-release-0.4.0.md)
for a complete installed-package example and publication verification. Native
model runners still execute from the repository; the wheel contains no weights.

Follow-up [improvement research](20-improvement-research-2026-11.md) adds 16
single-model Modal evaluations, four paired experiments, and quantization/license
findings. Its native-range comparisons use a distinct protocol from typed presets.

## Implemented behavior

- `Locator.plan()` preserves eligible candidate coverage before typed overlap
  arbitration. `redact_protected()` masks the original source with neutral
  PROTECTED placeholders. Plans are bound to the exact source and validate
  every supplied range/surface.
- Any overlapping component containing a secret becomes entirely irreversible.
  This deliberately sacrifices restoration of non-secret text in that component;
  it is more conservative than the partitioned policy considered in the proposal.
  Exact known-secret repetitions are protected throughout a source and across
  mapping leaves. See [ADR 0006](adr/0006-protection-plan.md).
- `protect_mapping()` supports explicit tuple-path field types, protects declared
  string fields without model inference, preserves keys and scalar types, and
  rejects missing/non-string policy targets. Known secrets cannot enter another
  leaf's vault under a different label.
- Strict plans reject dropped/unmapped diagnostics. `strict=False` explicitly
  retains the counters for exploration; it does not disable evaluation gates
  or establish complete detection. Exports contain offsets/types/counts, not
  source text or the private source-binding hash.
- Horizon Base uses the checked HF adapter. PII-Tracer loads reviewed custom
  code only after verifying its pinned SHA-256, preserves bidirectional attention,
  uses native Viterbi decoding, and checks complete windows before the native
  helper can truncate. MiniLM retains coarse native categories and checked windows.
- `rules-us` and `multi-encoder-us` enable cue-required SSN-shaped recognition
  under an explicit US profile. Basic [SSA structural exclusions](https://www.ssa.gov/employer/randomizationfaqs.html)
  are applied. This is not proof of issuance and carries no probability score.
  The default rule lane does not enable it.
- Legacy mapping diagnostics now survive even when every hit is rejected;
  secret-only mappings correctly report a change, and distinct integer/string
  dictionary keys are no longer collapsed.

## Usage

```python
from edgepii import Locator, redact_protected, protect_mapping, restore_mapping

locator = Locator.preset("rules")
source = "Contact ada@example.com. Password hunter2."
plan = locator.plan(source)
masked, vault = redact_protected(source, plan)

args = {"password": "hunter2", "note": "hunter2", "email": "ada@example.com"}
protected = protect_mapping(args, locator, field_types={("password",): "SECRET"})
assert protected.value["password"] == "<SECRET>"
assert protected.value["note"] == "<SECRET>"
assert "hunter2" not in str(protected.vault)
answer = restore_mapping(protected.value, protected.vault)
assert answer.value["email"] == args["email"]
# SECRET placeholders intentionally remain unresolved and cannot be restored.
```

Field paths contain actual dictionary keys/list indices, e.g.
`("users", 0, "password")`. Explicit fields override detector filters; other
leaves use the locator. Names of fields do not automatically imply sensitivity.
Numeric sensitive fields require an upstream schema decision, not silent
conversion. Exact secret repetition can over-mask common short values; it is
not inference about unseen or differently encoded credentials. Vault values
remain private caller-owned data.

## First-principles verification

The suite challenges the outcome using injected outputs and hand-calculated
oracles, including 100 seeded interval configurations. It covers:

- Union coverage under nesting, bridges, duplicates, and input permutations.
- Actual masked output and vault contents under secret overlaps and cross-leaf reuse.
- Unicode, combining marks, original-source binding, and rejected offset/surface mismatches.
- Dense-token tails, native decoder offsets, and independence from document-sensitivity gates.
- Reversible round trips, placeholder-literal collisions, and unique tree tokens.
- Strict diagnostics, country/cue/negative-ID controls, and unknown field-policy paths.
- Preserved dictionary key types and scalar structure; no detector call for declared fields.
- Custom model code hash verification before execution and native coarse-label preservation.

The final [full Modal verification](eval/validation/2026-11-05-protection-release/validation.json)
passed **244 tests, with one optional weight-dependent demo test skipped**.
It built and installed the wheel into a separate interpreter, exercised the
new protection and field-policy APIs from that wheel without importing Torch,
rebuilt the complete site, audited saved evidence, and checked desktop/mobile
browsers. [JUnit](eval/validation/2026-11-05-protection-release/junit.xml),
[Modal run](https://modal.com/apps/raphaelmansuy/main/ap-VlVDZd4Q32AKyakKf1oCaC).
Earlier [237-test verification](eval/validation/2026-11-05-protection-full/validation.json)
and [243-test verification](eval/validation/2026-11-05-protection-final/validation.json)
are retained with their own source hashes. GPU model inference is recorded
separately below; the skipped CPU demo does not replace those inference tests.

## Matched public measurements

All rows below are actual T4 measurements, 50 documents per public prefix,
with a shared input/gold selection digest within each run. Every typed model
has a model-only ablation in its JSON. SPY uses `government-id-v2` and its
original author-associated policy. No training, private calibration, or sealed
promotion run occurred. Public prefixes do not establish deployment performance
or statistical significance.

Native rows have no exact typed recall or public protection-plan projection.
Their containment is the union of native detection ranges. The character
masking precision column is against the declared gold, not a human task-utility
judgment. Warm p95 covers locate only: protection construction, redaction,
scoring assertions, loading, and transport are excluded. GPU MiB is peak
PyTorch allocated memory during evaluation/ablation, not total reservation or
process RSS. PII-Tracer uses a float16 backbone with float32 heads.

### Legal

[Completion manifest](eval/modal/spy-legal-50-9cbb4e97/run.json); [Modal run](https://modal.com/apps/raphaelmansuy/main/ap-UQpzXebFDdNNF1Xz8vRkD1).

| Preset / JSON | Exact recall | Containment | Character masking precision | Typed/native misses | Protection misses | Warm p95 | GPU MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [en-closed](eval/modal/spy-legal-50-9cbb4e97/spy-legal__en-closed-50.json) | 0.728 | 0.752 | 0.366 | 6 | 4 | 97.0 ms | 626 |
| [multi-encoder](eval/modal/spy-legal-50-9cbb4e97/spy-legal__multi-encoder-50.json) | 0.933 | 0.972 | 0.387 | 0 | 0 | 72.2 ms | 570 |
| [multi-encoder-base](eval/modal/spy-legal-50-9cbb4e97/spy-legal__multi-encoder-base-50.json) | 0.925 | 0.976 | 0.391 | 0 | 0 | 125.2 ms | 1231 |
| [tracer-native](eval/modal/spy-legal-50-9cbb4e97/spy-legal__tracer-native-50.json) | — | 0.992 | 0.261 | 0 | — | 207.1 ms | 1282 |
| [minilm-native](eval/modal/spy-legal-50-9cbb4e97/spy-legal__minilm-native-50.json) | — | 0.854 | 0.248 | 1 | — | 91.4 ms | 461 |

Misses above are high-severity complete-containment failures, not total exact false negatives.

| Typed lane | Selected / protected characters masked | Protected irreversible characters |
| --- | ---: | ---: |
| en-closed | 10663 / 10705 | 5 |
| multi-encoder | 10573 / 10583 | 149 |
| multi-encoder-base | 10511 / 10513 | 3 |

### Medical

[Completion manifest](eval/modal/spy-medical-50-7515b1aa/run.json); [Modal run](https://modal.com/apps/raphaelmansuy/main/ap-WaoszEfnv1GdwkJTzjGX0Y).

| Preset / JSON | Exact recall | Containment | Character masking precision | Typed/native misses | Protection misses | Warm p95 | GPU MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [en-closed](eval/modal/spy-medical-50-7515b1aa/spy-medical__en-closed-50.json) | 0.707 | 0.727 | 0.424 | 6 | 5 | 100.7 ms | 626 |
| [multi-encoder](eval/modal/spy-medical-50-7515b1aa/spy-medical__multi-encoder-50.json) | 0.887 | 0.942 | 0.456 | 10 | 10 | 69.2 ms | 570 |
| [multi-encoder-us](eval/modal/spy-medical-50-7515b1aa/spy-medical__multi-encoder-us-50.json) | 0.887 | 0.942 | 0.456 | 10 | 10 | 68.1 ms | 570 |
| [multi-encoder-base](eval/modal/spy-medical-50-7515b1aa/spy-medical__multi-encoder-base-50.json) | 0.887 | 0.955 | 0.458 | 6 | 6 | 94.0 ms | 1230 |
| [tracer-native](eval/modal/spy-medical-50-7515b1aa/spy-medical__tracer-native-50.json) | — | 0.965 | 0.288 | 0 | — | 181.7 ms | 1278 |
| [minilm-native](eval/modal/spy-medical-50-7515b1aa/spy-medical__minilm-native-50.json) | — | 0.846 | 0.287 | 0 | — | 73.7 ms | 461 |

Misses above are high-severity complete-containment failures, not total exact false negatives.

| Typed lane | Selected / protected characters masked | Protected irreversible characters |
| --- | ---: | ---: |
| en-closed | 10782 / 10801 | 8 |
| multi-encoder | 10490 / 10501 | 64 |
| multi-encoder-us | 10490 / 10501 | 64 |
| multi-encoder-base | 10514 / 10522 | 0 |

### Finance

[Completion manifest](eval/modal/gretel-finance-en-50-eceb01f7/run.json); [Modal run](https://modal.com/apps/raphaelmansuy/main/ap-eCThiCzEt0sXe8ZVFCsN41).

| Preset / JSON | Exact recall | Containment | Character masking precision | Typed/native misses | Protection misses | Warm p95 | GPU MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [multi-open](eval/modal/gretel-finance-en-50-eceb01f7/gretel-finance-en__multi-open-50.json) | 0.821 | 0.901 | 0.532 | 0 | 0 | 141.6 ms | 1284 |
| [multi-encoder](eval/modal/gretel-finance-en-50-eceb01f7/gretel-finance-en__multi-encoder-50.json) | 0.781 | 0.834 | 0.762 | 4 | 4 | 45.8 ms | 562 |
| [multi-encoder-base](eval/modal/gretel-finance-en-50-eceb01f7/gretel-finance-en__multi-encoder-base-50.json) | 0.755 | 0.795 | 0.760 | 4 | 4 | 71.3 ms | 1223 |
| [tracer-native](eval/modal/gretel-finance-en-50-eceb01f7/gretel-finance-en__tracer-native-50.json) | — | 0.974 | 0.477 | 0 | — | 120.3 ms | 1208 |
| [minilm-native](eval/modal/gretel-finance-en-50-eceb01f7/gretel-finance-en__minilm-native-50.json) | — | 0.887 | 0.481 | 1 | — | 40.3 ms | 461 |

Misses above are high-severity complete-containment failures, not total exact false negatives.

| Typed lane | Selected / protected characters masked | Protected irreversible characters |
| --- | ---: | ---: |
| multi-open | 4612 / 4618 | 8 |
| multi-encoder | 3379 / 3380 | 116 |
| multi-encoder-base | 3352 / 3369 | 120 |

## Decisions and remaining limits

- **Observed merge-induced coverage loss is removed by the opt-in plan.**
  ModernBERT legal misses change from 6 to 4 and medical from 6 to 5, matching
  pre-policy candidate coverage. Detection misses remain. The table exposes
  additional masking and irreversible characters rather than hiding the cost.
- **PII-Tracer is promising as a native-label candidate.** It has zero measured
  high-severity misses on all three prefixes and strong containment. Its
  character masking precision is lower than Horizon Small's here. SPY omits
  other people's identifiers, and native categories include types outside the
  public taxonomy, so that alone cannot establish unwanted masking or utility.
  A public typed mapping and an independent deployment freeze are still needed.
- **Larger is not uniformly better.** Horizon Base is slightly below Small's
  legal exact recall, equal on medical recall, and below it on finance recall.
  It reduces medical high-severity misses from 10 to 6 but uses more memory and
  does not meet a zero-miss criterion there.
- **The conservative US profile does not improve this medical row.** Retain
  that null result. It is not a reason to expand a numeric regex until the
  benchmark passes. Explicit sensitive fields can be protected even when
  values lack a cue or look structurally invalid.
- **MiniLM remains an efficiency experiment.** These are PyTorch/T4 results.
  ONNX/int8/Core ML/Apple Neural Engine/browser/target-CPU parity and latency
  remain unmeasured. Oversize-token warnings can arise during non-truncating
  length probes; checked inference windows still fit the effective budget.

The private case viewer, adjudicated target set, sealed group splits,
per-type/language calibration, conversation-corpus integration, training, and
quantized runtime promotion remain outstanding. The public PII-TRACE subset
is not automatically independent of PII-Tracer training. These tests do not
establish complete detection or anonymization. No production default changes.

## Reproduction

```bash
.venv/bin/python -m pytest tests/test_protection.py tests/test_country_profile.py tests/test_native_candidates.py
.venv/bin/modal run modal/models.py --corpus spy-legal --limit 50 --gpu T4 \
  --presets en-closed,multi-encoder,multi-encoder-base,tracer-native,minilm-native
.venv/bin/modal run modal/models.py --corpus spy-medical --limit 50 --gpu T4 \
  --presets en-closed,multi-encoder,multi-encoder-us,multi-encoder-base,tracer-native,minilm-native
.venv/bin/modal run modal/models.py --corpus gretel-finance-en --limit 50 --gpu T4 \
  --presets multi-open,multi-encoder,multi-encoder-base,tracer-native,minilm-native
.venv/bin/modal run modal/validate.py
```

Model/code pins and artifact hashes are in the
[phase-two manifest](research/model-manifest-phase2-2026-11-05.json) and
[native adapter](../modal/native_candidates.py). Native reports correctly
state that these models receive original source without confusable folding.
Permissive integration gates are not deployment risk floors.

The existing CLI leakage gate applies to selected typed/native predictions.
`protection_plan.high_severity_leaks` is a separate outcome diagnostic;
deployment policy must explicitly gate the path it actually sends upstream.
