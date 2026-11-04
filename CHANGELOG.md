# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-11-04

Closes the quasi-identifier gap and records the measurement the assessment asked
for. The `multi-open` lane had never been scored.

### Added

- `find_combinations(text)`, `has_combination(text)`, and `Combination`. Reports
  a set of ordinary fields that re-identifies a person, which a span list cannot
  express. `LocateResult.quasi` carries the finding beside the spans, and the
  demo shows it as a panel.
  - A field needs evidence. A numeric postcode needs a cue word, and a date is a
    date of birth only when the text says so, so an order id and a shipping date
    are not flagged. Nine negative cases are locked by tests.
  - The finding is advisory. The library does not mask a combination, because
    the right response depends on policy.
- The demo API returns `quasi`, and the demo page renders it with the risk level
  and a cited source. An e2e test proves it appears and disappears correctly.

### Changed

- `docs/13-first-public-score.md` records `multi-open` against `en-closed` on the
  same 100 SPY legal documents: **0.414 against 0.280**. `multi-open` raises both
  precision and recall, at 80 s of load time and about 3x the latency. Both lanes
  are measured now, so a caller can choose on evidence.

## [0.2.1] - 2026-11-04

Closes the three defects the November 2026 assessment found, and adds the
tool-call surface an agent needs.

### Added

- `mask_mapping(value, locator)` and `restore_mapping(value, vault)`: mask and
  restore a nested dict or list. Every string leaf is scanned, the tree shape is
  preserved, and `MaskedMapping.hits` records a field path and the types found
  without copying a value. A placeholder is unique across the tree
  (`<EMAIL_1_0>`, `<EMAIL_1_1>`), so two fields of the same type both round-trip.
- `edgepii.normalize`, with `fold()` and `needs_fold()`. Text is folded before
  matching: invisible characters are dropped, compatibility forms fold through
  NFKC, and a small explicit table folds cross-script confusables. Every folded
  character keeps its source index, so public offsets still index the caller's
  string.
- `locate(fold=...)`, on by default. `fold=False` restores the old behaviour.
- `locate(drop_unscored=...)` and the same field on the demo API.

### Changed

- A `min_score` floor now **keeps** a span that has no score. A grammar match
  carries no probability, so a floor cannot compare against it, and dropping it
  sent an email or a phone number to the model in the clear. The stricter
  behaviour is `drop_unscored=True`, and the demo shows it as a checkbox with
  the cost written beside it.
- The site claim check asserts both floor outcomes, so the guide cannot drift.

### Fixed

- A look-alike character no longer yields a partial span. Before this release,
  `Email аda@example.com` with a Cyrillic `а` returned a span starting after the
  character, so the mask read `Email а<EMAIL_1>` and the vault held an
  incomplete value. It now returns the whole address.
- A fullwidth `＠`, a zero-width space inside an address, and fullwidth digits
  are all found. They were missed completely.
- The non-breaking hyphen in a phone number folded to a hyphen, so the phone
  rule and the payment rule now agree on what a separator is.

## [0.2.0] - 2026-11-04

The loop the announcement describes is now complete. `redact` masks the outbound
prompt and `restore` puts the values back in the answer.

### Added

- `restore(text, vault, *, locator=None, types=None)` and `RestoreResult`. This
  is the inbound half of the mask loop. It reports `resolved`, `unresolved`, and
  `unknown`, so a response is never silently wrong.
  - Case drift: `<email_1>` resolves. A plain `str.replace` loop left it visible.
  - Spacing drift: `< EMAIL 1 >` and `<EMAIL-1>` resolve.
  - Token prefixes: `<EMAIL_10>` is never eaten by the `<EMAIL_1>` pattern.
  - Invented tokens are reported in `unresolved`, not left in the text.
  - `locator=` scans the raw response for PII the vault never held. That catches
    a hallucinated value or a leak the mask missed.
- `Span.to_dict()`, so one span exports without going through `LocateResult`.
- SPY, the standard out-of-distribution PII benchmark, as two corpora:
  `spy-legal` and `spy-medical`. First measured scores are in
  `docs/13-first-public-score.md`.
- BIO tag decoding (`spans_encoding: bio`) and `materialize_spy`, which fills the
  SPY templates with a fixed Faker seed so a run replays exactly.
- `MANIFEST.in`, so the sdist carries the docs, the changelog, and the license.
- A CI workflow at `site/workflow/ci.yml`: a 3.11/3.12/3.13 matrix, an artifact
  `twine check`, a wheel install that runs the public API, and a smoke run of
  `examples/run_local.py`. It is staged there rather than in
  `.github/workflows/` because pushing that path needs a token with the
  `workflow` scope. `site/README.md` records the one-time install.

### Changed

- Overlap resolution is now a sweep over spans sorted by start offset. It was a
  pairwise compare, which made a long document quadratic: 4 000 spans took
  0.77 s and now take 0.018 s. The phone rule on 42 000 characters went from
  2.09 s to 0.24 s, because the four region passes no longer feed a quadratic
  merge.
- `redact` rejects overlaps with one comparison per span instead of two loops.
- `zh-schema` pins the Release tag `v1.2` instead of the `master` branch. Design
  rule 8 says a floating branch is not a preset, and this preset broke that rule.
- The README no longer claims a workflow file that does not exist.

### Fixed

- A preset could float on a branch. `tests/test_principles.py` now fails if one
  does.
- The masking guide taught a `str.replace` loop that breaks on case drift. It now
  uses `restore` and shows what each failure looks like.

## [0.1.1] - 2026-11-04

### Added

- `edgepii.__version__`, so a caller can read the installed version without
  querying the package metadata.
- `src/edgepii/py.typed`, so type checkers read the annotations this package
  already ships.
- A test that locks the version to one source. The package, the demo, and the
  wheel metadata cannot drift apart.
- This changelog.

### Changed

- The version now lives in `edgepii/_version.py` and is declared `dynamic` in
  `pyproject.toml`. A release no longer needs two edits.
- The demo reads the same version instead of a second hard-coded copy.
- `LICENSE` ships in the wheel and the sdist, and the metadata reports
  `License-Expression: Apache-2.0`.
- The README renders on PyPI: image and doc links are absolute, and the install
  section leads with `pip install edgepii`.

### Fixed

- Publishing metadata was nearly empty, so the package could not be found by
  search. Author, keywords, classifiers, and project URLs are now set.

## [0.1.0] - 2026-11-04

### Added

- First public release on PyPI.
- `Locator.preset()` with the `rules`, `en-closed`, `multi-open`, `en-bert`,
  `phi-open`, and `zh-schema` lanes.
- `locator.locate()`, `locator.locate_many()`, and `redact()`.
- Taxonomy `2026.11`, with eleven public types in one YAML file.
- Exact-span evaluation on two pinned public corpora.
