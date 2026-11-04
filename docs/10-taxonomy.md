# Taxonomy version 2026.11

<!-- ste: descriptive -->

The taxonomy is the public type list. Model labels are private. The [span contract](01-span-contract.md) rejects a type that is not in the active version.

File in the future tree: `src/edgepii/taxonomies/2026.11.yaml`. This spec is the source of that file. Do not keep a second list in Python.

Version string: `2026.11`. A change that adds, removes, or renames a type creates a new version. A change that only adds a model label to a map does not.

## Classes

Each type has one class. The class sets merge rank and the redact rule. Higher severity wins an overlap. The number is rank, not a probability.

| Class | Rank | Redact |
| --- | --- | --- |
| `secret` | 40 | Irreversible mask. No vault entry. [ADR 0004](adr/0004-secrets-irreversible.md) |
| `gov_id` | 30 | Placeholder, vault on the caller. Fail closed if a second pass still sees the span |
| `payment` | 20 | Same as `gov_id` |
| `contact` | 10 | Placeholder |
| `person` | 10 | Placeholder |
| `quasi` | 0 | Off unless the caller lists the type. Easy to over-mask |

Rank 10 is a tie. The overlap rule then uses length, then score, then the type field `prefer`. See the [architecture](07-architecture.md).

## Types

| Type | Class | prefer | Notes |
| --- | --- | --- | --- |
| SECRET | secret | rule | Password, key, token, recovery code. Locate always. Never vault |
| GOV_ID | gov_id | rule | National id, passport, license, tax id. Patterns stay opt-in per country |
| PAYMENT | payment | rule | Card number after Luhn. IBAN after MOD-97 |
| EMAIL | contact | rule | Shape check |
| PHONE | contact | rule | libphonenumber parse |
| PERSON | person | model | Given name, surname, full name. Rules are weak |
| ADDRESS | person | model | Street through locality. Not a GPS point by itself |
| USERNAME | contact | model | A login name, not a display name, when the text marks an account |
| IP_ADDRESS | contact | rule | v4 and v6 |
| DATE_OF_BIRTH | quasi | model | A lone date is not this type. Context must mark birth |
| ORG | quasi | model | Off by default. Policy can enable it |

Eleven types are enough for v1. The model cards that emit 42 or 55 labels fold into this list through the map. A finer public list is a new taxonomy version, not a fork inside one adapter.

Fold examples:

| Model label, lower case | Public type |
| --- | --- |
| `email` | EMAIL |
| `phone_number`, `phonenumber`, `phone` | PHONE |
| `person`, `full_name`, `first_name`, `last_name`, `firstname`, `lastname` | PERSON |
| `address`, `street_address`, `street` | ADDRESS |
| `creditcardnumber`, `credit_debit_card`, `card_number`, `payment_card` | PAYMENT |
| `iban`, `bank_account` | PAYMENT |
| `ssn`, `national_id`, `national_id_number`, `passport_number`, `tax_id` | GOV_ID |
| `password`, `secret`, `api_key`, `access_token` | SECRET |
| `ip_address`, `ip`, `ipv4`, `ipv6` | IP_ADDRESS |
| `date_of_birth`, `dob` | DATE_OF_BIRTH |
| `username` | USERNAME |
| `companyname`, `organization` | ORG |
| `city`, `state`, `zipcode`, `postcode`, `country` | ADDRESS |
| `age`, `gender`, `date` with no birth cue | no map. Drop |

`city` alone is a known over-mask risk. V1 maps it to ADDRESS so the caller can disable ADDRESS. A later version can split CITY out after the golden set shows the cost.

Chinese schema labels for `zh-schema` use the same public types. The adapter sends Chinese schema names and maps the returned label back.

| Schema name passed to UIE | Public type |
| --- | --- |
| 姓名 | PERSON |
| 电子邮箱 | EMAIL |
| 手机号 | PHONE |
| 身份证号 | GOV_ID |
| 银行卡号 | PAYMENT |
| 详细地址 | ADDRESS |

Those Chinese names are schema prompts, not public types. The public result still says `PERSON` or `EMAIL`.

## Caller subset

The caller can pass `types=["EMAIL", "PHONE", "PERSON"]`. The locator asks each detector only for labels that map to that subset. A closed encoder cannot drop a head output by request. The locator filters after the map. An open-schema model receives only the mapped label strings for the subset. That keeps Lane G honest: the type list is an input.

A name outside `2026.11` raises `UnknownType` before any detector runs.

## Thresholds

The library ships no score threshold. A threshold is a decision about a specific corpus. Any number the library picked would be a guess, and a guess in the merge path is a heuristic. The caller measures a floor on its own data and passes `min_score`.

A span with `score = None` has no measured confidence. A `min_score` drops it, because it cannot meet a floor. With no `min_score`, every span stays. That keeps the two cases apart: "I want everything" and "I want only what a validator or a model scored above this line".

```python
result = locator.locate(source, types=["PERSON"], min_score=0.9)
```

| Score | Meaning | Source |
| --- | --- | --- |
| `1.0` | A published checksum or parser confirmed the slice | ISO 7812 Luhn, ISO 13616 MOD-97, RFC 4291, libphonenumber validity |
| `null` | A grammar matched and no validator exists | RFC 5321 shape, RFC 3986 shape, cue-plus-value |
| A model number | The checkpoint confidence for this span | The checkpoint, not this library |

A rule hit with a checksum is not automatically trusted. It still passes the slice check and the overlap merge. A rule hit with no checksum reports `score = None`. The library never invents a probability there, because a fixed 0.8 would order spans by nothing.

A model threshold is also the checkpoint author's. The adapter does not add a second cut-off. A caller who wants a stricter floor passes `min_score`, and the eval report shows what that floor costs.

## Placeholder shape

The redact helper builds placeholders as `<TYPE_N>`. `N` starts at 1 for each type in the call. Two different slices of type PERSON become `<PERSON_1>` and `<PERSON_2>`. The same slice later in the same call reuses the same placeholder.

The angle brackets are deliberate. They are rare in prose and easy to test. The helper does not use a bare `PERSON_1`, because that string can already occur in the source.

## What stays out of 2026.11

Blood type, religion, ethnicity, sexuality, and political view appear on some cards. V1 does not ship them. They are sensitive, and a synthetic card score is a poor reason to detect them by default. Add them in a later version with a written policy and a slice in the golden set.
