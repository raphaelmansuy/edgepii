# Assessment, November 2026

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

| Item | Why it is not in 0.2.1 |
| --- | --- |
| ONNX `multi-open` lane | Needs an artifact pin and an ADR for the fixed label set |
| Surrogate replacement | Changes what leaves the host, so it needs its own ADR |
| Quasi-identifier combinations | Needs a layer above spans, not a detector change |
| Semantic leakage | Out of scope for a span detector, and now stated as a limit |
| CI at `.github/workflows` | Blocked on a token with the `workflow` scope |
