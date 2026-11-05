"""Verify a PyPI release on Modal using a fresh, isolated installation.

.venv/bin/modal run modal/verify_release.py --version 0.4.0
"""

import json
from pathlib import Path
import re

import modal

ROOT = Path(__file__).resolve().parents[1]
app = modal.App("edgepii-pypi-release-verification")
image = (modal.Image.from_registry("python:3.11-slim-bookworm")
         .add_local_file(ROOT / "scripts/verify_install.py", "/verify_install.py"))


@app.function(image=image, cpu=2, memory=2048, timeout=600)
def verify(version: str) -> dict:
    import hashlib
    import subprocess
    import sys
    from urllib.request import urlopen

    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version must be a final major.minor.patch release")
    endpoint = f"https://pypi.org/pypi/edgepii/{version}/json"
    with urlopen(endpoint, timeout=30) as response:
        metadata = json.load(response)
    assert metadata["info"]["version"] == version
    files = [{"filename": f["filename"], "sha256": f["digests"]["sha256"],
              "url": f["url"], "yanked": f["yanked"]} for f in metadata["urls"]]
    assert len(files) == 2 and all(not f["yanked"] for f in files)
    for artifact in files:
        assert artifact["url"].startswith("https://files.pythonhosted.org/")
        with urlopen(artifact["url"], timeout=60) as response:
            assert hashlib.sha256(response.read()).hexdigest() == artifact["sha256"]
    commands = [
        [sys.executable, "-m", "venv", "/tmp/edgepii-pypi"],
        ["/tmp/edgepii-pypi/bin/python", "-m", "pip", "--isolated", "install",
         "--index-url", "https://pypi.org/simple", "--no-cache-dir",
         "--report", "/tmp/edgepii-pypi-install.json", f"edgepii=={version}"],
        ["/tmp/edgepii-pypi/bin/python", "-I", "/verify_install.py", "--version", version],
    ]
    steps = []
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        steps.append({"command": command, "exit_code": result.returncode,
                      "output": (result.stdout + result.stderr)[-16000:]})
        if result.returncode:
            break
    passed = all(step["exit_code"] == 0 for step in steps)
    installed = []
    report_path = Path("/tmp/edgepii-pypi-install.json")
    if report_path.exists():
        for entry in json.loads(report_path.read_text())["install"]:
            if entry["metadata"]["name"] == "edgepii":
                info = entry["download_info"]
                assert info["url"] in {f["url"] for f in files}
                assert info["archive_info"]["hashes"]["sha256"] in {f["sha256"] for f in files}
                installed.append({"version": entry["metadata"]["version"], **info})
    assert not passed or (len(installed) == 1 and installed[0]["version"] == version)
    return {"mode": "published-pypi", "provider": "modal", "passed": passed,
            "version": version, "metadata_url": endpoint, "files": files,
            "installed": installed, "steps": steps, "python": sys.version,
            "smoke_sha256": hashlib.sha256(Path("/verify_install.py").read_bytes()).hexdigest()}


@app.local_entrypoint()
def main(version: str, out: str = "docs/eval/validation"):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version must be a final major.minor.patch release")
    destination = Path(out) / ("pypi-" + version.replace(".", "-"))
    destination.mkdir(parents=True, exist_ok=False)
    result = verify.remote(version)
    (destination / "validation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("Published release verification:", result["passed"], destination)
    if not result["passed"]:
        raise SystemExit("Published release verification failed; inspect the saved evidence")
