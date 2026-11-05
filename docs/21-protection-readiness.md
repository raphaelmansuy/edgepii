# Protection readiness and release 0.5.0

This implements the first part of P0 from the
[improvement research](20-improvement-research-2026-11.md): explicit gates for
the emitted protection output, document-level leakage counts, and a measured
stage audit. The audit identifies all ten Horizon medical containment losses
at taxonomy projection. No detector weights or public category meanings change.

## Install

```bash
.venv/bin/pip install --upgrade edgepii==0.5.0
.venv/bin/python -c 'import edgepii; print(edgepii.__version__)'
```

Use Python 3.11 or newer and create the virtual environment first if needed.
The rules lane and gate API need no model runtime. See
[PyPI 0.5.0](https://pypi.org/project/edgepii/0.5.0/) and the
[protection API example](19-release-0.4.0.md#use-the-new-protection-api).

## Select the output that is actually sent

```python
from edgepii.eval.gates import GatePolicy, check_gates

policy = GatePolicy(
    output="protection",
    max_leaks=0,
    max_leaking_documents=0,
    max_unmapped=0,
    min_containment=0.9,
)
# result = check_gates(saved_report, policy)
```

`output="selected"` retains the previous default. For `output="protection"`,
leakage, document leakage, containment, and masking precision come from
`protection_plan`. The gate rejects an absent plan, a partial document count,
inconsistent gold counts, invalid counters, and undefined requested metrics.
The unmapped-prediction budget defaults to zero for this path. Invalid source
offsets remain limited by `max_dropped=0`.

`min_recall` still means exact typed recall from the selected span output.
`min_containment` is a separate full-span floor. `min_masking_precision`
compares covered gold characters with masked characters under that corpus's
annotation policy; it is not a human utility score. Criteria apply separately
to every requested slice, including minority slices.

Count limits must be nonnegative integers; NaN, fractional counts, and booleans
are rejected. Historical policy serialization retains its original three
fields when the new options are unused, so archived gate checks still replay.

An explicitly larger `max_unmapped` budget can be used for diagnostic studies.
It does not change `Locator.plan(strict=True)`, which still rejects nonzero
unmapped diagnostics. A gate pass means the declared report criteria passed;
it does not establish complete detection or deployment qualification.

### CLI and Modal

The actual medical readiness experiment uses these criteria:

```bash
.venv/bin/modal run modal/models.py --corpus spy-medical --limit 50 --gpu T4 \
  --presets multi-encoder --gate-output protection --max-leaks 0 \
  --max-leaking-documents 0 --min-containment 0.9
```

**Expected result: exit 1.** The
[saved report](eval/modal/spy-medical-50-2a6ed546/spy-medical__multi-encoder-50.json)
contains ten high-severity misses, ten leaking documents among 39 applicable
documents, and 234 unmapped predictions. These are actual model outputs,
not injected gate failures. The
[completion manifest](eval/modal/spy-medical-50-2a6ed546/run.json) records
`quality-gates-failed`. Failed quality criteria retain their evidence and do
not turn into integration passes.

The local CLI exposes the same controls:
the model example requires the `hf` extra (`pip install 'edgepii[hf]==0.5.0'`).

```bash
.venv/bin/python -m edgepii.eval.cli --preset multi-encoder \
  --corpus spy-medical --limit 50 --gate-output protection --max-leaks 0 \
  --max-unmapped 0 --min-containment 0.9 --out /tmp/readiness.json
```

The report is written before exit 1. The printed table continues to show typed
selected spans and identifies that protection is the gated path. Native-label
experiments have no public protection plan and cannot claim this readiness result.
Other new controls are `--min-masking-precision` and
`--max-leaking-documents`. The example thresholds are experimental caller
criteria, not established deployment floors.

## What the stage audit established

The audit uses a checked HF model with rules disabled. It caches each distinct
original/folded input, then replays the same predictions through trimming,
mapping, eligibility, selection, and actual protection construction. Model
variation cannot explain a difference between downstream stages in one case.
Every range is validated on the original source, and protection output/vault
invariants are exercised. Only counts, labels, and coverage flags are exported.

Each experiment uses 50 records and the same selection fingerprints as the
earlier studies. Both original and confusable-folded branches produced the
same aggregate results on these prefixes. Every document needed one distinct
inference input here; the independent Unicode test exercises two distinct inputs.

| Model / corpus | Raw native containment / high-severity misses | After whitespace trim | After public mapping | Selected | Protected |
| --- | ---: | ---: | ---: | ---: | ---: |
| Horizon / medical, 311 gold | 305 / 0 | 305 / 0 | 295 / 10 | 295 / 10 | 295 / 10 |
| Horizon / legal, 254 gold | 247 / 0 | 247 / 0 | 247 / 0 | 247 / 0 | 247 / 0 |
| ModernBERT / legal, 254 gold | 220 / 4 | 176 / 4 | 173 / 6 | 173 / 6 | 173 / 6 |

Reports: [Horizon medical](eval/stages/spy-medical-multi-encoder-50-0bea79b7.json),
[Horizon legal](eval/stages/spy-legal-multi-encoder-50-a6d83bcf.json),
[ModernBERT legal](eval/stages/spy-legal-en-closed-50-66c2f279.json).
Modal runs: [medical](https://modal.com/apps/raphaelmansuy/main/ap-319oaF7vYjPWIX15QwYXtp),
[legal](https://modal.com/apps/raphaelmansuy/main/ap-4sb8sQO5IgcM8aj6vXB2f4).

**Medical conclusion:** ten gold identifiers were fully covered by native
ranges and cease to be fully covered after public projection. Trimming,
eligibility, and overlap selection add no high-severity misses in that study.
This isolates the observed coverage loss; it does not make the native
category predictions correct or justify mapping all account/medical IDs to GOV_ID.
Model-specific category definitions and an independently adjudicated set
remain the next requirements for a mapping change.

**Legal conclusion:** whitespace trimming can change full-span containment
without adding high-severity misses, and projection adds two ModernBERT
high-severity misses. These model-only results differ from the earlier
rules-assisted preset measurements. Neither finding justifies deleting
normalization or trimming globally to improve one score.

The [recomputed audit summary](research/protection-readiness-summary-2026-11-05.json)
also re-gates a historical Horizon legal report: the legacy zero-leak check
passes, while strict protection readiness rejects the unmapped predictions.
That is a counterfactual check of saved measurements, with no edited historical
report or new inference claim.

## Document leakage

New reports contain `high_severity_documents` and
`high_severity_leaking_documents`. The latter is also recorded inside
`protection_plan`. A document counts once even when several high-severity gold
spans are missed. The applicable denominator is documents with high-severity
gold, rather than every document in the sample.

This separates a system that misses ten identifiers in one record from one
that exposes ten different records. Source-free aggregate counts do not
establish independence, real-world prevalence, or statistical confidence.

## First-principles verification and remaining work

Tests build a real selected-versus-protected counterexample: a short secret
wins typed arbitration inside a broader candidate, while the emitted protection
union covers the whole gold range and keeps the component irreversible. The
selected gate fails and the protection gate passes. A second test introduces
unmapped diagnostics and verifies readiness rejection.

Additional tests cover partial/missing plans, undefined/NaN metrics, invalid
counts, minority slices, document leakage, saved CLI failures, Unicode folding,
trimming between adjacent fragments, and inference reuse across stages.
The installed-wheel smoke checks exercise the new gates without importing Torch.

```bash
.venv/bin/modal run modal/models.py --corpus spy-medical --limit 50 --gpu T4 \
  --presets multi-encoder --stage-audit
.venv/bin/python scripts/audit_protection_readiness.py
.venv/bin/modal run modal/validate.py
```

The private case viewer, adjudicated target set, model-specific taxonomy
decisions, trained routing policy, and sealed promotion run remain future work.
These gates make incomplete or leaking evaluations explicit; they do not
repair detection or silently broaden category meanings.

## Release validation

The [pre-publication full Modal run](eval/validation/2026-11-05-protection-gates-050/validation.json)
passed **286 tests, with one optional weight-dependent demo test skipped**.
It built and installed the 0.5.0 wheel, exercised the new gate controls without
Torch, replayed historical evidence and the new stage audits, rebuilt the site,
and tested desktop/mobile browsers.
[JUnit](eval/validation/2026-11-05-protection-gates-050/junit.xml),
[Modal run](https://modal.com/apps/raphaelmansuy/main/ap-mvvKSv7MImgEn89p1lIeas).
The real-inference quality-gate rejection above is separate from this passing
regression suite.

Both distributions are published on PyPI. Their hashes match the committed
source build in the [artifact manifest](eval/releases/edgepii-0.5.0.json).
The [fresh PyPI installation on Modal](eval/validation/pypi-0-5-0/validation.json)
passed **all 12 installed-package checks**, including selected-versus-protected
gating and rejection of unmapped output. Both published files were downloaded
and hash-checked. [Modal run](https://modal.com/apps/raphaelmansuy/main/ap-5LIGWDGxgVObgRLnSosFAI).
The artifact source commit is recorded in the manifest; subsequent changes
record this publication evidence.
The [final site/browser verification](eval/validation/2026-11-05-gates-050-published-site/validation.json)
passed **17 tests with no skips** on Modal, including the publication evidence
and readiness guide at desktop and mobile sizes.
