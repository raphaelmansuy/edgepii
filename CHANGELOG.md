# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

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
