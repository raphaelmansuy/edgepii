# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

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
- A CI workflow with a 3.11/3.12/3.13 matrix, an artifact install check, and a
  smoke run of `examples/run_local.py`.

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
