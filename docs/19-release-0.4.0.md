# Release 0.4.0

EdgePII 0.4.0 includes coverage-preserving protection, explicit field policies,
irreversible secret propagation, checked model windows, deterministic overlap
handling, and the corrected SPY evaluation protocol. See the
[measured results](18-protection-and-model-results.md) for model limitations and
the [changelog](https://github.com/raphaelmansuy/edgepii/blob/main/CHANGELOG.md)
for the complete changes.

## Install or upgrade

Python 3.11 or newer is required. In an existing virtual environment:

```bash
.venv/bin/pip install --upgrade edgepii==0.4.0
.venv/bin/python -c 'import edgepii; print(edgepii.__version__)'
```

The printed version must be `0.4.0`. The distribution is available as a wheel
and source archive on [PyPI](https://pypi.org/project/edgepii/0.4.0/).
For a fresh environment, run `python3.11 -m venv .venv` first.

## Use the new protection API

```python
from edgepii import Locator, protect_mapping, redact_protected, restore

locator = Locator.preset("rules")
source = "Contact ada@example.com."
masked, vault = redact_protected(source, locator.plan(source))
assert "ada@example.com" not in masked
assert restore(masked, vault).text == source

protected = protect_mapping(
    {"password": "hunter2", "note": "hunter2", "email": "ada@example.com"},
    locator,
    field_types={("password",): "SECRET"},
)
assert protected.value["password"] == protected.value["note"] == "<SECRET>"
assert "hunter2" not in str(protected.vault)
```

The field policy protects the declared string and its exact repetitions even
when the detector cannot recognize a credential. Secrets cannot be restored.
Use the [API reference](06-library-api.md) and
[protection policy](adr/0006-protection-plan.md) to choose the appropriate path.

## Optional model runtimes

The rules lane installs only `phonenumbers` and `pyyaml`. Model presets need
separate extras, for example:

```bash
.venv/bin/pip install --upgrade 'edgepii[hf]==0.4.0'
```

Horizon Small/Base and the US profile are opt-in. Native PII-Tracer and MiniLM
experiments run from the repository using [Modal](../modal/README.md); they are
not public typed SDK presets. No model weights are packaged in the wheel.
The measured public prefixes do not establish complete detection or production
qualification for a new deployment.

## Release verification

CI tests Python 3.11, 3.12, and 3.13, builds wheel/source distributions, checks
their metadata, and runs the installed wheel and examples in clean environments.
The [0.4.0 pre-publication Modal run](eval/validation/2026-11-05-pypi-0-4-0/validation.json)
passed **244 tests with one optional weight-dependent demo test skipped**, built
and checked the installed wheel, and exercised the updated site in desktop and
mobile browsers. [JUnit](eval/validation/2026-11-05-pypi-0-4-0/junit.xml),
[Modal run](https://modal.com/apps/raphaelmansuy/main/ap-sDp1pdopdtyt0dsiIz9Gla).
`scripts/verify_install.py` verifies the installed distribution version, public
exports, Unicode offsets, masking/restoration, source binding, strict diagnostics,
explicit field policy, cross-leaf secret exclusion, the opt-in country profile,
and absence of Torch from the rules lane.

After upload, `modal/verify_release.py` retrieves versioned PyPI metadata,
downloads both published artifacts, verifies their SHA-256 hashes, installs
`edgepii==0.4.0` from PyPI in a fresh environment without its package cache,
and checks the installed wheel using that same script:

```bash
.venv/bin/modal run modal/verify_release.py --version 0.4.0
```

Publication evidence is recorded after the upload and installation check.
