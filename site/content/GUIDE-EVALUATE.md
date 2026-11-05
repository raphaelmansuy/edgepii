# Score it yourself

The [5 November research update](15-research-update-2026-11.md) and
[implementation results](16-grounded-improvement-plan.md#11-completion-record)
contain the latest pinned Modal experiments. New reports include containment
and coverage diagnostics. SPY's corrected `government-id-v2` materialization
has different input values from the historical scores; compare models only
within a matched selection digest and protocol.

<!-- ste: procedural -->

A card figure is not evidence. This page runs the library against two public PII corpora and shows
how to read the report.

## Why you would do this

Every vendor reports a number. Most of those numbers come from a split that the model trained on.
That number tells you what the model memorised, not what it will do on your text.

The harness here pins two corpora, so two people can score the same preset on the same bytes and
get the same answer. Nothing is averaged across corpora, because two corpora are two different
measurements.

## Install the eval extra

```bash
.venv/bin/pip install "edgepii[eval]"
```

That adds `pyarrow`, which reads the Parquet files. The rest of the library does not need it.

## Run a score

```bash
python -m edgepii.eval.cli --preset rules --corpus nemotron-pii --limit 2000 --print
```

You should see a table like this:

```text
preset=rules revision=rules corpus=nemotron-pii@b70ffaf5ff39 taxonomy=2026.11 limit=2000
slice           docs   gold   pred     tp    fp    fn      P      R     F1     F2 leak
all             2000   5890   2396   1565   831  4325  0.653  0.266  0.378  0.301  589
intl            2000   6157   2742   1891   851  4266  0.690  0.307  0.425  0.345  595
structured      2000   6191   2751   1767   984  4424  0.642  0.285  0.395  0.321  638
unstructured    2000   5666   2244   1533   711  4133  0.683  0.271  0.388  0.308  543
us              2000   5890   2396   1565   831  4325  0.653  0.266  0.378  0.301  589
```

The run downloads about 150 MB on the first call and caches it under `~/.cache/edgepii`. Every later
run reads the cache.

## Read the columns

| Column | Meaning |
| --- | --- |
| `docs` | Documents scored in this slice |
| `gold` | Gold spans the map put in scope |
| `pred` | Spans the library returned |
| `tp` | Exact matches: same type, same start, same end |
| `fp` | Predicted spans with no match |
| `fn` | Gold spans with no match |
| `P`, `R` | Precision and recall, from those counts |
| `F1` | The harmonic mean. The primary metric |
| `F2` | Recall weighted twice. A leak costs more than an over-mask |
| `leak` | Gold spans in a high-severity class that no prediction covers |

Exact match is strict on purpose. A prediction that covers 14 of 15 characters is not a true
positive. It is a shifted span, and one missing character can leave an address resolvable.

## What the `--limit` flag does

`--limit` takes the first N documents **of each slice**, not the first N of the corpus.

This matters. The Nemotron locals sit in two blocks of 50 000, so a corpus-wide limit of 500 reads
only the `us` block and reports an empty `intl` slice with a precision and recall of `1.000`. A
perfect score on zero documents is the most misleading number a report can print. The limit is per
slice to prevent it.

## Add a model lane

```bash
.venv/bin/pip install "edgepii[hf]"
python -m edgepii.eval.cli --preset en-closed --corpus nemotron-pii --limit 500 --print
```

```text
preset=en-closed revision=3d0f39eceaf0 corpus=nemotron-pii@b70ffaf5ff39 taxonomy=2026.11 limit=500
slice           docs   gold   pred     tp    fp    fn      P      R     F1     F2 leak
all              500   1343   1867   1326   541    17  0.710  0.987  0.826  0.916    2
```

Recall near 0.99 and precision 0.71. The lane masks nearly every capitalised run, so it finds names
and also invents some.

## Compare in domain against out of domain

Run the same preset on the finance corpus:

```bash
python -m edgepii.eval.cli --preset en-closed --corpus gretel-finance-en --limit 400 --print
```

```text
all              400    982   2701    250  2451   732  0.093  0.255  0.136  0.189   38
```

F1 falls from 0.826 to 0.136. Per type, `PERSON` falls from 0.995 to 0.048. That gap is the single
most useful fact about this checkpoint, and no model card contains it.

> [!WARNING]
> Do not average a Nemotron score with a Gretel score. They measure two corpora with two label
> distributions. A single number would hide the gap that matters.

## Write your own corpus

A corpus is data, not code. Add a row to `src/edgepii/eval/corpora.yaml`:

```yaml
corpora:
  my-corpus:
    title: My support tickets
    role: Out of domain. Hand labels on the real channel.
    repo_id: my-org/my-corpus
    revision: <full commit sha>
    file: data/test.parquet
    bytes: 1234567
    sha256: <sha256 of the file>
    license: CC-BY-4.0
    text_column: text
    spans_column: spans
    spans_encoding: json
    labels:
      email_address: EMAIL
      person_name: PERSON
    drop:
      - labels: [order_id]
        reason: An internal id. No class in the taxonomy, and it is not PII.
```

Then run it:

```bash
python -m edgepii.eval.cli --preset rules --corpus my-corpus --print
```

Three rules keep the score honest:

1. **Pin the bytes.** A `sha256` that does not match stops the run. A moved file makes an old score
   unreadable.
2. **Name every label.** A gold label the map does not name is counted as `unknown` and printed. It
   is never folded into a neighbour, because a silent fold inflates recall.
3. **Write a reason for every drop.** A label you exclude needs a sentence, so a reader can disagree
   with the decision.

## What the report holds

The report is JSON. It holds counts, the corpus pin, the preset revision, the taxonomy version, and
the environment. It holds **no source text**, so it is safe to commit.

| Field | Meaning |
| --- | --- |
| `corpus_sha256`, `corpus_revision` | Which bytes were read |
| `preset_revision` | Which weights, if any |
| `corpus_diagnostics` | What the map did to every label in the whole file |
| `documents_scored` | Documents in the `all` slice |
| `slices.<name>.per_type` | Counts and ratios per public type |
| `slices.<name>.high_severity_leaks` | Secret, gov id, and payment spans that survived |

## A floor is your decision

The library ships no minimum score. If you want one, measure it. Here is the real sweep on 500
Nemotron documents, run on 4 November 2026:

| Lane | Floor | Spans | P | R | F1 |
| --- | --- | --- | --- | --- | --- |
| `rules` | none | 586 | 0.602 | 0.213 | 0.314 |
| `rules` | 0.50 | 392 | 0.411 | 0.097 | 0.157 |
| `rules` | 0.90 | 392 | 0.411 | 0.097 | 0.157 |
| `en-closed` | none | 797 | 0.764 | 0.979 | 0.858 |
| `en-closed` | 0.90 | 783 | 0.765 | 0.963 | 0.853 |

Two lessons, and both are the opposite of the obvious guess.

**On the rule lane a floor makes things worse.** Every rule except card and IP reports no score, so a
floor at any value above zero removes the email and phone hits that were carrying the lane. Precision
falls as well as recall, because the spans that survive are the noisy card matches. Do not put a floor
on `rules`.

**On the model lane a floor barely helps.** Every model span has a score, and the checkpoint is
confident about almost all of them. A floor of 0.90 costs 14 spans and 0.005 F1. It does not fix the
over-masking that holds precision at 0.765, because the wrong spans are scored high too.

That is the argument for measuring a floor rather than picking one. To reproduce the table:

```python
from pathlib import Path
from edgepii import Locator
from edgepii.eval.corpora import build_docs, ensure_file, load_spec, read_raw
from edgepii.eval.runner import score_docs

spec = load_spec("nemotron-pii")
path = ensure_file(spec, Path.home() / ".cache" / "edgepii")
docs, _ = build_docs(read_raw(path), spec, set(spec.labels.values()))

for preset in ("rules", "en-closed"):
    locator = Locator.preset(preset)
    for floor in (None, 0.5, 0.9):
        row = score_docs(locator, docs[:500], "all", set(spec.labels.values()), min_score=floor)
        report = row.to_dict()
        print(preset, floor, report["predicted_spans"], report["precision"], report["recall"])
```

> [!WARNING]
> A floor is not a safety dial. In both lanes above it lowered F1. The only way to know what it does
> to your text is to run it on your text.

## Next

- Read the [full public score](../evaluation/) with the failure analysis
- Read the [corpora reference](../doc-corpora/) for every label fold and every drop
- Read the [evaluation spec](../doc-evaluation/) for the metric definition
