# Assessment, November 2026

**5 November research-audit erratum:** the historical SPY materializer filled
`ID_NUM` with RIPE organization handles and mapped them to `GOV_ID`. The 37
high-severity gold spans in the 50-document run all came from that bucket.
The recorded counts are reproducible, but are not validated government-ID
leakage measurements. SPY also labels author-associated identifiers rather than
all identifiers. Read the [research update](15-research-update-2026-11.md) and
[new plan](16-grounded-improvement-plan.md) for the correction and fresh evidence.
Historical JSON files are preserved unchanged.

<!-- ste: descriptive -->

This file records the state of `edgepii`, measured against the research
published up to November 2026. It separates what works, what was a defect, and
what the field has moved on from. Every defect below was reproduced on this
host, not inferred from a paper.

Version 0.2.1 closes D1, D2 and D3, and adds the tool-call surface. Sections 2
and 3 keep the original finding so a reader can check the fix against the
problem. Section 7 records the verification.

The run date is 4 November 2026. The host is an arm64 CPU with no accelerator.

## 1. Where the library stands

The engineering is sound and the numbers are real. Measured on the shipped code:

| Property | Value | How it was checked |
| --- | --- | --- |
| Public API | 10 names, one result shape | `edgepii.__all__` |
| Source size | 2 660 lines | `wc -l src/edgepii` |
| Tests | 120 | `pytest --collect-only` |
| Rules latency | 4.5 ms per 1 560 characters | 20 calls, warm |
| Wheel install | rules lane pulls no ML framework | `torch` absent from `sys.modules` |
| Span invariant | holds on accents, CJK, emoji ZWJ | direct probe |
| Long text | 7 000 characters, 500 spans, 0 dropped | direct probe |
| Merge cost | linear in span count | 8 000 spans in 0.057 s |

The span contract is the library's real asset. It is checkable, it is enforced,
and it survives the cases that usually break a chunked NER pipeline. Very few
small PII libraries can say the same.

The outbound and inbound halves now both exist. `redact` masks, `restore` puts
values back, and `restore` reports what it could not fix. That closed the gap
between the announcement and the API.

## 2. Defects that a reader can reproduce

These are not design opinions. Each one is a measurement.

### D1. A partial span silently leaks a character

The highest-severity defect. A Cyrillic `а` (U+0430) in front of an email makes
the rules lane return a span that starts after the confusable character:

```python
src = "Email \u0430da@example.com"      # Cyrillic a, then da@example.com
masked, vault = redact(src, loc.locate(src).spans)

# masked = "Email \u0430<EMAIL_1>"
# vault  = {"<EMAIL_1>": "da@example.com"}
```

A reviewer sees an address that looks masked. One character of it is still in
the text, and the vault holds an incomplete value. This is worse than a miss,
because a miss is visible and this is not.

Related, and simpler: a fullwidth `＠` (U+FF20) and a zero-width space inside an
address both produce no span at all. A non-breaking hyphen in a phone number is
still spanned, so the two rules disagree with each other.

Research position: [Special-Character Adversarial Attacks](https://arxiv.org/html/2508.14070v1)
measures zero-width injection at 54.2% success and cross-script homoglyphs at
58.7% against open models. [Mimecast](https://www.mimecast.com/blog/5-keystrokes-that-defeat-a-privacy-filter/)
shows the same five-keystroke attack against DLP filters. The defence is
NFKC plus a TR39 visual-confusable skeleton pass before detection, and the span
must then be reported on the **original** offsets.

This is the one defect that breaks the library's own promise, because the
promise is `source[start:end] == text` and the text is not the value the caller
believes it is.

### D2. `min_score` removes the types that have no score

```python
loc.locate(src, min_score=0.5)
# keeps PAYMENT (score 1.0)
# drops EMAIL, PHONE, SECRET (score None)
```

For a redaction tool, "dropped" means "sent to the model in the clear". The
behaviour follows from a deliberate principle, that a grammar match reports no
invented probability. The principle is right. The consequence is a trap: the one
knob a caller reaches for when tuning precision silently deletes recall on the
highest-confidence types.

### D3. Escaped PII in a tool call is invisible

```python
'{"q": "ada\\u0040example.com"}'    # → no span
```

An agent that serialises arguments with non-ASCII escaping sends an address the
detector never sees. `restore` handles placeholders inside JSON correctly, so
the inbound path is fine; the outbound scan is the gap.

## 3. What the field moved to, and the library has not

### 3.1 The tool-call plane

This is the largest gap between the library and the 2026 threat model.

The library treats text as a string a human wrote. An agent's dominant leak path
is now a **structured tool call**: arguments assembled from earlier context and
sent to a third-party server before any output guardrail runs.

Published measurements on this:

- [ToolMinimize](https://arxiv.org/html/2608.24957) found that **81–88% of tool
  calls include unnecessary privacy-sensitive data** under default prompts
  across GPT-4o, Claude 3.5 Sonnet, and Llama-3.3-70B. Explicit privacy
  instructions still leave 36–76% over-sharing.
- [Agents That Know Too Much](https://arxiv.org/html/2606.26627) names the
  arguments, the responses, and the side effects as three separate surfaces.
- [Openlayer](https://www.openlayer.com/blog/llm-output-pii-detection) states the
  asymmetry plainly: a guardrail at the output layer never sees the arguments,
  because the call already executed.
- Production gateways already ship this
  ([IntentGate](https://github.com/IntentGate-app/intentgate-gateway/blob/main/internal/pii/mcp_request.go),
  [Occludra](https://occludra.ai/blog/mcp-gateway-secure-agent-tool-calls)),
  and independently control the outbound and inbound direction, because blocking
  an outbound argument is safe while blocking an inbound result breaks the agent.

`edgepii` has every primitive needed for this and no surface for it. A caller
can pass a JSON string to `locate` and get spans, but the offsets are into the
serialised text, not into the argument values, and nothing maps a span back to a
field path.

The shape that would close it:

```python
masked_args, vault = redact_mapping(tool_args, locator)   # walks a dict or a list
restore_mapping(response_args, vault)
```

Field paths replace character offsets in the journal, so the caller can say
"the `customer.email` field was masked" without copying the value.

### 3.2 Surrogate replacement

Typed placeholders are a meta-token that violates the distribution the model was
trained on. [SurrogateShield](https://arxiv.org/html/2606.29567) measures the
cost: type-consistent surrogates preserve **94.85%** of semantic utility against
**81.59%** for placeholder redaction. It also reports that placeholders leak by
shape: in an informed-adversary probe, Presidio's `[PERSON]` markers allowed
1.53% per-value recovery from surrounding context, while surrogates allowed 0%.

`edgepii` already returns exact spans, so a surrogate strategy is a change to one
function, not to the detector. [Veil-Then-Reveal](https://arxiv.org/html/2610.22800)
shows the structured half: format-preserving encryption keeps a card number
card-shaped and a date date-shaped, which is what keeps the model useful.

### 3.3 Quasi-identifier combinations

The taxonomy excludes the `quasi` class, so `DATE_OF_BIRTH` and `ORG` are off by
default. A prompt such as:

```text
Patient born 1985-03-14, ZIP 94110, male, referred for follow-up.
```

returns **no spans at all**. Each field is benign alone. Together, ZIP + date of
birth + sex re-identifies most of a population, which is Sweeney's k-anonymity
result and the rule SurrogateShield ships as ten combination patterns.

A span-level detector alone cannot express "this combination is the risk". That
needs one more layer above the span list, and it is the most useful thing the
taxonomy could gain.

### 3.4 Semantic, not lexical, leakage

[PromptPET](https://arxiv.org/html/2607.02932v1) shows that a profiler attacking
a PII-redacted prompt still recovers 1.93 profile labels per query. "I was
recently diagnosed with depression and need a therapist near Mountain View"
contains no PII after masking, and still discloses a health condition. No span
detector closes that, and the library should not pretend otherwise. It belongs in
a limits section, so a reader does not over-trust the mask.

## 4. Prioritised plan

| Priority | Item | Why it is first |
| --- | --- | --- |
| P0 | Confusable-safe detection (D1) | It breaks the span promise silently |
| P0 | Decide `min_score` behaviour (D2) | One flag currently disables recall |
| P1 | `redact_mapping` for tool arguments | The dominant 2026 leak path |
| P1 | ONNX `multi-open` lane | 0.535 F1 on SPY at 704 ms CPU |
| P2 | Surrogate strategy | +13 points of downstream utility |
| P2 | Quasi-identifier combination check | Catches the re-identification case |
| P3 | Escaped-input scan (D3) | Cheap, closes an agent hole |
| P3 | Stress-test benchmark | Turns a paper into a feature |

### On the ONNX lane

The library ships `multi-open`, which is GLiNER2, and never installed it in any
measurement here. A quantised ONNX export of the same checkpoint reports
**0.534 F1 on SPY-200 at 704 ms CPU** ([okasi](https://huggingface.co/okasi/gliner2-privacy-filter-pii-multi-onnx)),
against the 0.490 the PyTorch path reports on the same slice, and against
`en-closed` at 0.281 measured here.

That is the single largest score improvement available, it needs no retraining,
and it removes `torch` from the deployment. The trade is a pinned ONNX artifact
plus a `labels`-at-export-time constraint, which conflicts with the
change-the-type-list-at-call-time property `multi-open` exists for. Worth
recording as an ADR before building it.

## 5. What not to change

Three things are correct and a future contributor may try to "fix" them:

1. **No invented scores.** A shape match reports `None`. That is what makes the
   eval numbers mean something. Fix D2 by changing the floor's behaviour, not by
   inventing confidence.
2. **Secrets never enter the vault.** A restore would write a credential into the
   next log. Keep it.
3. **No silent normalisation inside `locate`.** D1 is tempting to solve by
   normalising the source in place. That moves every offset. Normalise for
   matching, report on the original.

## 6. Sources

| Topic | Source |
| --- | --- |
| Tool-call over-sharing, 81–88% | [ToolMinimize, arXiv:2608.24957](https://arxiv.org/html/2608.24957) |
| Agent privacy surfaces | [Agents That Know Too Much, arXiv:2606.26627](https://arxiv.org/html/2606.26627) |
| Output-layer blind spot | [Openlayer](https://www.openlayer.com/blog/llm-output-pii-detection) |
| Unicode and homoglyph evasion | [arXiv:2508.14070](https://arxiv.org/html/2508.14070v1), [Mimecast](https://www.mimecast.com/blog/5-keystrokes-that-defeat-a-privacy-filter/) |
| Surrogate utility, k-anonymity | [SurrogateShield, arXiv:2606.29567](https://arxiv.org/html/2606.29567) |
| Format-preserving surrogates | [Veil-then-Reveal, arXiv:2610.22800](https://arxiv.org/html/2610.22800) |
| Semantic profiling after masking | [PromptPET, arXiv:2607.02932](https://arxiv.org/html/2607.02932v1) |
| Robustness under distribution shift | [Mind the Gap, arXiv:2609.03464](https://arxiv.org/html/2609.03464v1) |
| Privacy-utility evaluation | [TAU-EVAL](https://aclanthology.org/2025.emnlp-demos.16.pdf) |
| ONNX GLiNER2 on SPY | [okasi ONNX export](https://huggingface.co/okasi/gliner2-privacy-filter-pii-multi-onnx) |
| SPY leaderboard | [GLiNER2-PII, arXiv:2605.09973](https://arxiv.org/abs/2605.09973) |

## 7. What 0.2.1 changed

Each item names the test that locks it. A regression fails the suite.

### D1 is closed: folding with a map back to the source

`normalize.py` folds text before matching and records the source index of every
folded character. The locator runs the detectors on the folded text, then maps
each hit back onto the caller's string. Three classes of character fold:

| Class | Example | How |
| --- | --- | --- |
| Invisible | `U+200B` zero width space | Dropped, and the span covers it |
| Compatibility | `＠` `U+FF20`, fullwidth digits | NFKC |
| Cross-script confusable | Cyrillic `а` `U+0430` | An explicit table |

The table is small and explicit on purpose. A general skeleton would change text
the caller did not ask to change, and the offsets have to stay defensible.

Result on the original defect:

```text
before  "Email а<EMAIL_1>"   vault {"<EMAIL_1>": "da@example.com"}
after   "Email <EMAIL_1>"    vault {"<EMAIL_1>": "аda@example.com"}
```

The mask is complete and the vault holds the full value. Spans still satisfy
`source[start:end] == text`, because folding never escapes the locator.

Cost on clean text is zero. SPY legal on the rules lane is **unchanged at 0.325**
precision 0.358 and recall 0.298, measured before and after the change.

Locked by `tests/test_hardening.py`. The e2e and model lanes were re-run: 145
tests pass, and `en-closed` still returns correct offsets with folding on.

### D2 is closed: a floor keeps a span that has no score

`merge_spans` now keeps a `None` score when a floor is set. The stricter
behaviour is `drop_unscored=True`. The demo shows the difference as a checkbox
with the cost written beside it, and the site claim check asserts both outcomes.

### D3 is closed: decode before the scan

`mask_mapping` walks a decoded tree, so `ada\u0040example.com` is scanned as
`ada@example.com`. A caller holding raw JSON calls `json.loads` first, which is
the step that produces a value worth scanning.

### The tool-call plane now has a surface

`mask_mapping` and `restore_mapping` take a nested dict or list and return a copy.
The public shape is three fields:

- `MaskedMapping.value`, the masked tree.
- `MaskedMapping.vault`, unique per tree.
- `MaskedMapping.hits`, a journal of `path` and `types` with no values.

A defect found while building it, and fixed: `redact` numbers each type from one
within a single string, so two leaves both produced `<EMAIL_1>` and restoring
wrote the first value into both fields. Each token now carries a leaf index,
`<EMAIL_1_0>` and `<EMAIL_1_1>`, and the round trip returns both values.

### Still open

| Item | Status |
| --- | --- |
| ONNX `multi-open` lane | Open. The PyTorch lane is now measured; an ONNX artifact would cut the 80 s load |
| Surrogate replacement | Open. Changes what leaves the host, so it needs its own ADR |
| Quasi-identifier combinations | **Closed in 0.3.0.** `find_combinations` and `LocateResult.quasi` |
| Semantic leakage | Out of scope for a span detector, and stated as a limit |
| CI at `.github/workflows` | Open. Blocked on a token with the `workflow` scope |

## 8. What 0.3.0 changed

### The quasi-identifier gap is closed

`quasi.py` reports a set of ordinary fields that singles a person out. The case
the assessment recorded now returns a finding instead of nothing:

```text
"Patient born 1985-03-14, ZIP 94110, male"  ->  spans: ()   quasi: zip_dob_sex, high
```

The check needs evidence before a field counts. A bare five-digit number is an
order id as often as a ZIP, and a bare date is a shipping date as often as a
birth date. A first version flagged `Order 48291 shipped on 2026-11-04` as
`zip_dob`, which would train a caller to ignore the check. A numeric postcode now
requires a cue word, and a date of birth requires a birth cue. Nine negative
cases are locked by `tests/test_quasi.py`, and the panel is covered by a browser
test that proves it appears and disappears.

### The missing measurement is recorded

The `multi-open` lane had never been scored, which the assessment named as the
biggest credibility gap. On the same 100 `spy-legal` documents:

| Preset | P | R | F1 |
| --- | --- | --- | --- |
| `en-closed` | 0.181 | 0.622 | 0.280 |
| `multi-open` | 0.283 | 0.768 | **0.414** |

`multi-open` is 48% better on this slice and improves both precision and recall.
The cost is real: 80 s to load and about 3x the latency. `en-closed` stays the
default for a fast first pass, and the file now records both numbers so a caller
chooses on evidence rather than on a recommendation.

## 9. Engineering follow-up, 5 November 2026

The current assessment is **a useful alpha with a strong output contract and
substantial domain-dependent detection errors**. Correct offsets prove which
characters were detected. They do not prove that all sensitive characters were
detected, or that the remaining context cannot identify a person.

The committed `en-closed` reports illustrate this distinction. Exact-span recall
is 0.987 on 500 Nemotron documents, with two high-severity leaks, and 0.255 on
400 Gretel finance documents, with 38 high-severity leaks. These are separate
corpora and sample sizes, not a paired model experiment. They support a need for
domain-specific validation, not a universal accuracy claim. Their report files
are `docs/eval/nemotron-pii__en-closed-500.json` and
`docs/eval/gretel-finance-en__en-closed-400.json`.

### Changes implemented in this follow-up

- GLiNER2 loads its weights, configuration, and tokenizer from one pinned Hub
  snapshot. Both GLiNER adapters fail with `DetectorLoadError` rather than retry
  without a revision when loading raises `TypeError`.
- Both GLiNER adapters move to the requested device and enter evaluation mode.
  The Hugging Face adapter preserves device strings, including `cuda:1` and
  `mps`, instead of converting every non-`cuda` request to CPU.
- GLiNER adapters carry the model's reported text into the existing slice
  checker, so an offset/surface disagreement is counted and dropped.
- The GLiNER2 extra includes its local inference dependencies. The base
  `gliner2==2.1.0` package alone now provides an SDK without the full ML runtime.
- An actual Modal run found a Transformers 4 compatibility failure with the
  pinned ModernBERT tokenizer (`TokenizersBackend`). The runtime now pins
  Transformers 5.22.1 and PEFT 0.21.2, and the HF extra requires Transformers 5.
- The evaluation CLI can enforce an exact-span recall floor, high-severity
  leakage ceiling, and invalid-offset ceiling on every requested slice. It
  saves failed reports and exits nonzero. Empty slices and unmapped gold labels
  cannot silently pass.
- Reports record selected-input and package-source digests, type subset,
  score floor, normalization policy, package versions, devices, and individual
  inference-call latency percentiles. Existing report fields remain present.
- `modal/models.py` provides explicit private SDK inference and a matched-corpus
  comparison of the rules baseline, ModernBERT, and GLiNER2. It uses a weight
  cache, one model load per container, scale-to-zero, and a container cap. The
  manual GitHub workflow retains evaluation reports when gates fail.

The runtime follows Modal's current [weight storage](https://modal.com/docs/guide/model-weights)
and [lifecycle](https://modal.com/docs/guide/lifecycle-functions) guidance.
Deterministic outcome graders and explicit acceptance criteria follow the
evaluation approach described in [Anthropic's January 2026 engineering guidance](https://www.anthropic.com/research/demystifying-evals-for-ai-agents).
Here, exact source offsets are a direct grader; a generative judge adds no
useful certainty to that check.

### Remaining work before a production claim

1. Freeze acceptance criteria on development data, then evaluate held-out
   examples representative of the deployment's languages, entity types, and
   document lengths. The current deterministic public prefixes are exploratory.
   Report uncertainty and per-type failures before ranking close model results.
2. Audit token budgets across all model adapters. Character-count windows do
   not establish a token-count bound for arbitrary Unicode or dense identifiers.
   A valid returned offset does not prove the model processed the whole window.
3. Measure complete request latency and cost, including cold start, data
   transfer, concurrency, and real production request sizes. The new latency
   percentiles describe warmed `locate` calls, not a service latency SLO.
4. Keep cloud inference an explicit data-boundary choice. A Modal call receives
   the unmasked source. It is not an automatic privacy-preserving replacement
   for local inference. No public HTTP endpoint or cloud fallback was added.

The default Modal comparison records baseline quality. Its zero recall floor
and disabled leakage ceiling are **not production acceptance criteria**. See
the [Modal guide](../modal/README.md) for explicit gate configuration and the
privacy boundary.

### Measured Modal result

The completed [Modal run](https://modal.com/apps/raphaelmansuy/main/ap-1KV9hXEQfviTU8cmJfYR8Q)
evaluated 50 SPY legal documents containing 254 in-scope gold spans. Both model
lanes used a Tesla T4; the rules baseline used four CPU threads. Every run used
the same materialized inputs and gold: selection SHA-256
`2a1d0aa44fe3bf8fa022ce3521e6030d7948e45c2f41462696858b9d8812d748`.
All three package-source and deployment-source fingerprints also match.

- [Rules report](eval/modal/spy-legal__rules-50.json): precision 0.281,
  recall 0.283, F1 0.282, F2 0.283; 37 high-severity leaks. Warm p95 8.1 ms.
- [ModernBERT report](eval/modal/spy-legal__en-closed-50.json): precision 0.163,
  recall 0.606, F1 0.258, F2 0.393; 37 high-severity leaks. Warm p95 96.6 ms.
- [GLiNER2 report](eval/modal/spy-legal__multi-open-50.json): precision 0.262,
  recall 0.768, F1 0.391, F2 0.554; 28 high-severity leaks. Warm p95 292.1 ms.

All runs reported zero invalid offsets. GLiNER2 is the stronger recall candidate
on this sample, with 16.1 percentage points more recall and nine fewer
high-severity leaks than ModernBERT. Its p95 inference latency is about three
times higher. Precision remains low for both models. No default model is
changed on the strength of 50 exploratory documents.

Applying the example release policy of 90% recall and zero high-severity leaks
to these saved reports correctly rejects all three presets. The default
integration gates passed because they do not impose those quality targets.
Local validation completed with **175 tests passed and two skips**: the optional
Playwright browser module was unavailable, and converted site images were
absent. The manual GitHub workflow was syntax-checked locally; it has not been
dispatched in GitHub.
