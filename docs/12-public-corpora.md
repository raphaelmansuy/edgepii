# Public corpora

<!-- ste: descriptive -->

This file names the public PII corpora that the scorer reads, the license of each, and the fold from each external gold label into taxonomy `2026.11`. The data lives in [corpora.yaml](../src/edgepii/eval/corpora.yaml). That file is the only list.

A score is replayable only when the bytes are pinned. Each corpus row carries a repository id, a commit revision, a file name, a byte count, and a `sha256`. A download that does not match the pin stops the run. It does not warn and continue, because a moved file makes an old score unreadable.

## The two corpora

| Key | Corpus | License | Role | Size |
| --- | --- | --- | --- | --- |
| `nemotron-pii` | [nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII) test split | CC-BY-4.0 | In domain. The `en-closed` checkpoint trains on this distribution | 100 000 documents |
| `gretel-finance-en` | [gretelai/synthetic_pii_finance_multilingual](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual) English test split | Apache-2.0 | Out of domain. Finance documents and SWIFT messages | 2 891 documents |

Both are fully synthetic. Neither holds real personal data. Both licenses allow redistribution and commercial use, so either one can sit in a public gate.

### Why these two

The [evaluation spec](09-evaluation.md) asks for one slice that the checkpoint card names and one slice it does not. A card score on a set that the checkpoint trained on is in domain. It is not evidence for a new domain.

- `nemotron-pii` is the in-domain slice. The `antoniogr7/pii-identifier-v0.1` card and its `preprocessing.json` both name `nvidia/Nemotron-PII` as the source, so this corpus measures the ceiling of that checkpoint rather than its transfer.
- `gretel-finance-en` is the out-of-domain slice. A finance document with SWIFT fields and a chat transcript looks nothing like a synthetic persona note. A preset that passes `nemotron-pii` and fails here has learned a template, not a type.

SPY is the third name in the research note. The public release is not reachable without an access grant from this writing environment, so it is not a pin. The [gaps](#gaps) section records that.

## What the map keeps and drops

Each corpus uses its own label names. The map folds a label into one public type, or it drops the label with a written reason. A label that the file does not name at all is a third case: the report prints it under `unknown_labels`. A silent fold would inflate recall, so the run refuses to guess.

| Public type | Nemotron labels | Gretel labels |
| --- | --- | --- |
| `PERSON` | `first_name`, `last_name` | `name`, `first_name`, `last_name` |
| `EMAIL` | `email` | `email` |
| `PHONE` | `phone_number`, `fax_number` | `phone_number` |
| `ADDRESS` | `street_address` | `street_address` |
| `PAYMENT` | `credit_debit_card` | `credit_card_number`, `iban`, `bban` |
| `GOV_ID` | `ssn`, `national_id`, `tax_id` | `ssn`, `passport_number`, `driver_license_number` |
| `SECRET` | `password`, `api_key` | `password`, `api_key` |
| `IP_ADDRESS` | `ipv4`, `ipv6` | `ipv4`, `ipv6` |
| `USERNAME` | `user_name` | `user_name` |
| `DATE_OF_BIRTH` | `date_of_birth` | `date_of_birth` |
| `ORG` | `company_name` | `company` |

The drops fall into five groups. The reason is in the YAML next to the label, so the decision travels with the data.

| Group | Examples | Why it is not in scope |
| --- | --- | --- |
| Address components | `city`, `state`, `county`, `postcode`, `country` | One postal address would become five gold spans. The taxonomy type is street through locality, so scoring each component would double count |
| A date with no birth cue | `date`, `date_time`, `time` | Taxonomy `2026.11` has no `DATE` type. `DATE_OF_BIRTH` needs a birth cue |
| Sensitive attribute | `gender`, `race_ethnicity`, `blood_type`, `political_view` | [The taxonomy](10-taxonomy.md) keeps these out of v1 on purpose |
| Account or internal id | `account_number`, `customer_id`, `employee_id`, `bank_routing_number` | No class in the type list, and an internal id is not PII by default |
| Trace identifier | `url`, `http_cookie`, `mac_address`, `license_plate` | Outside taxonomy `2026.11` |

Two of these deserve a note.

`cvv` and `pin` are dropped although they look secret. A `SECRET` span needs a cue word and a value. A bare four digit code has no cue, so scoring it would measure a detector that the library does not claim. The [rule audit](../README.md#every-rule-names-its-source) forbids a rule with no source.

`city` alone is a known over-mask risk that the taxonomy already records. Nemotron labels a city inside an address, so a keep would score a span the library never returns.

## Nested gold spans

A corpus row can nest two labels. Gretel puts a person name inside a company name, and a street address inside a person name. The locator returns one non-overlapping list, so gold must be one list too. The harness keeps the longer range and counts the row under `rows_with_overlapping_gold`.

Nemotron holds one such row in 100 000. Gretel holds 1 866 in 2 891. The Gretel number is a property of that generator, and it is why a Gretel score is not comparable to a Nemotron score by type.

## Run a score

```bash
pip install -e ".[eval]"                                  # pyarrow
python -m edgepii.eval.cli --preset rules --corpus nemotron-pii --limit 500 --print
python -m edgepii.eval.cli --preset rules --corpus gretel-finance-en --print
```

| Flag | Meaning |
| --- | --- |
| `--preset` | A preset name from `presets.py`, or `rules` |
| `--corpus` | A key from `corpora.yaml` |
| `--limit` | Take the first N documents of each slice |
| `--slice` | Score one slice. Repeat the flag for more |
| `--types` | Score a type subset |
| `--cache` | Where the pinned file lives. Default `~/.cache/edgepii` |
| `--out` | The report path. Default `docs/eval/<corpus>__<preset>-<limit|full>.json` |

`--limit` cuts a prefix per slice, not per corpus. A corpus-wide prefix would read only the `us` block of Nemotron-PII, because the locales arrive in two blocks of 50 000, and it would report an empty `intl` slice with a perfect precision and recall of `1.000`. A prefix per slice keeps every slice populated.

## The report

The report is JSON. It holds counts, the two pins, the taxonomy version, and the environment. It holds no source text. A span score is a number; the text that produced it stays out of the file.

| Field | Meaning |
| --- | --- |
| `preset`, `preset_revision` | Which lane, and the checkpoint revision |
| `corpus`, `corpus_revision`, `corpus_sha256`, `corpus_license` | The pin the run read |
| `document_limit` | `null` for a full run |
| `documents_scored` | Documents in the `all` slice. Compare it with `document_limit` |
| `corpus_diagnostics` | What the map did to every gold label in the whole file |
| `corpus_diagnostics_scope` | A reminder that the diagnostics read the file, not the limited run |
| `slices.<name>` | Counts and ratios for one slice |
| `slices.<name>.per_type` | The same counts per public type |
| `slices.<name>.high_severity_leaks` | Gold spans in `secret`, `gov_id`, or `payment` that no prediction covers |
| `seconds` | Wall time for the scoring pass, without the download |

`corpus_diagnostics` is the audit of the map. It reports the count of in-scope spans, out-of-scope spans, dropped labels, unknown labels, bad offsets, and rows with nested gold. A change to `corpora.yaml` shows up here before it shows up in a ratio.

## The score is per document

The scorer runs `locate`, then compares the spans of that one document with the gold of that one document, then adds the counts. It never pools every gold span into one list.

A pooled list would score two documents as one string. A span in document B could match a gold span in document A when the two texts share a prefix, and the report would claim a hit for a document that holds no such text. `tests/test_eval_corpora.py` locks that case with a fixed detector.

The metrics are the ones in the [evaluation spec](09-evaluation.md): exact span, per type and micro, with `miss`, `wrong_type`, `shift`, and `extra` as exclusive counts that add up to the false negatives.

## Gaps

| Gap | State |
| --- | --- |
| SPY legal and medical prose | Not a pin. The public release did not answer from this environment on 4 November 2026. It stays the named third slice |
| A human-read slice of the real channel | Open. A synthetic corpus cannot replace it |
| Chinese | Open. No public Chinese PII corpus is pinned yet |
| Floors | Open. A score is not a gate until [phase 9](08-implementation-plan.md) writes the number |
| `bank_routing_number` | Dropped on Gretel as an internal bank id. On Nemotron the same label is also dropped. A later taxonomy version can decide whether an ABA routing number is personal |
