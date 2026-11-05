# EdgePII models on Modal

The [latest implementation results](../docs/18-protection-and-model-results.md)
add `multi-encoder-base`, `multi-encoder-us`, `rules-us`, `tracer-native`, and
`minilm-native`. Native experiments retain their label namespaces and use
containment metrics. Reports for typed lanes also evaluate actual output from
the opt-in protection plan without repeating inference. Locate latency excludes
that protection/scoring work. Peak GPU allocation is recorded separately.

For published-package verification, run
`.venv/bin/modal run modal/verify_release.py --version 0.4.0`. This uses a fresh
virtual environment, checks PyPI artifact hashes, and exercises the installed
protection APIs without loading models. See the
[release guide](../docs/19-release-0.4.0.md).

The [post-release improvement research](../docs/20-improvement-research-2026-11.md)
adds evaluation-only `masker-mini-native`, `masker-int4-native`, `ettin-native`,
and `horizon-native`. Use `--gpu cpu` for int4. `--paired` compares per-case native
coverage; `--paired --quantized --gpu cpu` checks float/int4 parity. These modes
do not expose typed SDK inference or change library presets.

Version 0.5.0 adds `--gate-output protection`, `--min-containment`,
`--min-masking-precision`, `--max-unmapped`, and `--max-leaking-documents`.
Use `--stage-audit --presets multi-encoder --gpu T4` for source-free attribution
of model-only coverage through each processing stage. See the
[readiness guide](../docs/21-protection-readiness.md); expected quality-gate
failures retain their reports and exit nonzero.

`models.py` runs the existing pinned encoder models on Modal. It supports
`rules`, `en-closed` (ModernBERT), `multi-open` (GLiNER2), `multi-encoder`
(Horizon mmBERT), and `multi-boundary` (GLiNER2.5). These new presets are
experimental. `opf-native` is an explicitly separate native-label containment
experiment using the pinned official OPF Viterbi runtime; it is not a public
typed SDK preset. The default library
presets still run locally. Model weights and public corpus downloads are cached
in the `edgepii-model-cache` Volume; model instances load once per container.

## Compare models

From the repository root, with an authenticated Modal account:

```bash
.venv/bin/pip install -e '.[dev,eval,modal]'
.venv/bin/modal setup
.venv/bin/modal run modal/models.py --corpus spy-legal --limit 200
```

The rules baseline uses a CPU; the model lanes use an L4. Each model evaluates
the same deterministic prefix of every corpus slice. The selection digest
includes the actual documents, gold spans, and slice memberships. A mismatch
aborts the comparison. JSON reports go to `docs/eval/modal/` and contain counts,
configuration, runtime package versions, model load time, and warm latency
percentiles. They contain no document text, extracted values, or document IDs.
Each run has a unique subdirectory and completion manifest. Every candidate
first runs actual-inference Unicode, masking, restoration, repeated-value, and
rule-disabled smoke checks; these verify contracts, not perfect detection.

```bash
.venv/bin/modal run modal/models.py --corpus spy-legal --limit 50 --gpu T4 \
  --presets rules,en-closed,multi-open,multi-encoder,multi-boundary,opf-native
```

New SPY runs use `government-id-v2` and declare the author-associated annotation
policy. They must not be compared numerically to legacy materializations as if
the gold inputs were unchanged. OPF reports containment rather than forcing
its eight native categories into narrower public types. A positive typed recall
floor cannot be applied to that native experiment.

`--limit` is per slice; multilingual corpora may process more unique documents
than that number. `--presets en-closed,multi-open` skips the rules baseline;
`--gpu T4` selects another supported Modal GPU. Containers scale to zero after
60 idle seconds and each parameter configuration is capped at one container.
The cache Volume persists between runs.

`--gpu cpu` runs the model lanes on Modal CPUs for a quality-only comparison
when GPU capacity is unavailable. The report records the actual hardware.

This command incurs Modal compute and storage charges. It uses public corpora.
An HF token is optional for these public models; if `HF_TOKEN` exists locally,
it is passed as a Modal Secret.

## Quality gates

Choose acceptance criteria from deployment needs and a development split, then
freeze them before evaluating a held-out test set:

```bash
# Example policy, not a claim about the shipped models' accuracy:
.venv/bin/modal run modal/models.py --corpus spy-legal --limit 200 \
  --presets en-closed,multi-open --min-recall 0.90 --max-leaks 0

# The same gates are available for local runs:
.venv/bin/python -m edgepii.eval.cli --preset rules \
  --corpus gretel-finance-en --max-leaks 0 --max-dropped 0 --print
```

Every requested slice must pass. Empty slices, unknown gold labels, and invalid
offsets fail by default. Recall floors and leakage ceilings are caller policy:
the default Modal command uses a zero recall floor and no leakage ceiling to
collect baseline measurements. Passing that default is an integration check,
not a production safety certification. Failed gates save their reports and exit
nonzero. Runtime/model load failures stop the run instead of reporting success.

The manual GitHub Actions workflow `model-eval.yml` runs the same comparison
and retains reports for 14 days even when a gate fails. Configure repository
secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` before dispatching it. It has
no push, pull request, or scheduled trigger. Its example default policy (90%
recall and zero high severity leaks) is deliberately stricter than the baseline
measurement command; the current models may fail it.

Latency measures individual `locate` calls after one synthetic warm-up. It
excludes model download, container startup, network transport, and scoring. The
reported load time excludes container startup. CPU baseline and GPU model
latencies represent different hardware, so they do not isolate model efficiency.
Public prefix samples are exploratory; they are not randomized, representative
production traffic or evidence of freedom from training-data contamination.

The GPU image pins NumPy 1.26.4 and Arrow 20.0.0. Arrow 26 required NumPy 2 at
import despite its package metadata allowing installation into the older
runtime. An import preflight and `pip check` now run during image building.
The native OPF runtime loads the pinned checkpoint's `original/` directory;
its root contains the separate Transformers conversion. Initial failed runs
remain in their manifests, and invalid source spans still fail offset gates.

## Full verification on Modal

```bash
.venv/bin/modal run modal/validate.py
# Recheck final evidence links and both site viewports after saving a report:
.venv/bin/modal run modal/validate.py --site-only
```

The full mode builds a wheel, installs it into an isolated interpreter, checks
the source/mask/restore/no-torch contract, regenerates the entire static site,
audits completed model reports, and runs every test with real Chromium.
Source-file hashes, dependency versions, JUnit output, and browser screenshots
are retained under `docs/eval/validation/`. The optional HF demo-browser test
requires local model weights and is covered separately by actual GPU model
inference checks. `site-only` is labeled as a narrower follow-up, not a full
library test result.

## Private SDK inference

```bash
.venv/bin/modal deploy modal/models.py
```

```python
import modal

Model = modal.Cls.from_name("edgepii-models", "Model")
worker = Model.with_options(gpu="L4")(preset="multi-open", device="cuda")
result = worker.locate.remote("Contact Ada Lovelace at ada@example.com.")
```

There is no public HTTP endpoint. Calls use Modal credentials. Cloud inference
sends the original source to Modal and returns spans containing source values;
choose this boundary deliberately for sensitive workloads. The service does not
log source text or store inputs in its cache. Deployment of this app does not
change `Locator.preset` or add an automatic cloud fallback. Inputs are bounded
to 100,000 characters; this service is not a complete PII gateway.

## Design references

The deployment follows Modal's [model weight storage guidance](https://modal.com/docs/guide/model-weights),
[container lifecycle hooks](https://modal.com/docs/guide/lifecycle-functions),
and [authenticated SDK lookups](https://modal.com/docs/guide/trigger-deployed-functions).
The development loop uses deterministic, task-specific graders and explicit
outcome criteria, consistent with [Anthropic's January 2026 evaluation guidance](https://www.anthropic.com/research/demystifying-evals-for-ai-agents).
For exact-span PII, gold offsets provide a direct grader; a generative judge
would add uncertainty to this contract.
