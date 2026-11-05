"""Run the full offline suite, real browser tests, and site checks on Modal."""

from pathlib import Path
import json
import modal

ROOT=Path(__file__).resolve().parents[1]
app=modal.App("edgepii-first-principles")
image=(
    modal.Image.from_registry("python:3.11-slim-bookworm")
    .apt_install("imagemagick","librsvg2-bin")
    .pip_install("setuptools==80.9.0","wheel","pytest==9.2.0",
                 "phonenumbers==9.0.42","pyyaml==6.0.3","faker==40.44.0",
                 "pyarrow==26.0.1","fastapi==0.162.0","httpx==0.28.1",
                 "uvicorn==0.54.0","playwright==1.56.0")
    .run_commands("python -m playwright install --with-deps chromium")
    .add_local_dir(ROOT,"/workspace",ignore=[".git/**",".venv/**","**/__pycache__/**",
                    ".pytest_cache/**","site/dist/**","**/*.egg-info/**"])
)


@app.function(image=image,cpu=4,memory=8192,timeout=1800)
def validate(site_only: bool=False) -> dict:
    import os
    import subprocess
    import sys
    import xml.etree.ElementTree as ET
    import importlib.metadata
    import hashlib
    os.chdir("/workspace")
    artifacts=Path("/tmp/edgepii-validation")
    artifacts.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONPATH="/workspace/src",EDGEPII_TEST_ARTIFACTS=str(artifacts))
    source_files = sorted(path for folder in ("src", "tests", "site", "modal", "docs")
                          for path in Path(folder).rglob("*")
                          if path.is_file() and path.suffix in {".py", ".md", ".yaml", ".css", ".js", ".html"}
                          and "dist" not in path.parts and not str(path).startswith("docs/eval/"))
    source_hashes = {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}
    wheel_smoke = '''import sys, pathlib
from edgepii import Locator, redact, restore
import edgepii
assert not pathlib.Path(edgepii.__file__).is_relative_to('/workspace')
source = 'Card 4242424242424242 and email ada@example.com.'
result = Locator.preset('rules').locate(source)
assert all(source[s.start:s.end] == s.text for s in result.spans)
masked, vault = redact(source, result.spans)
assert '4242424242424242' not in masked and 'ada@example.com' not in masked
assert restore(masked, vault).text == source
from edgepii import redact_protected, protect_mapping
plan = Locator.preset('rules').plan(source)
protected, protection_vault = redact_protected(source, plan)
assert restore(protected, protection_vault).text == source
tree = protect_mapping({'a':'hunter2','b':'hunter2'}, Locator.preset('rules'), field_types={('a',):'SECRET'})
assert 'hunter2' not in str(tree.value) and not tree.vault
assert 'torch' not in sys.modules
print('Installed wheel source, mask/restore, and no-torch invariants passed')
'''
    steps=[]
    commands=[[sys.executable,"-m","pip","install","--no-deps","--no-build-isolation","-e","."],
              [sys.executable,"-m","pip","wheel","--no-deps","--no-build-isolation",".","--wheel-dir",str(artifacts)],
              [sys.executable,"-m","venv","--system-site-packages","/tmp/edgepii-wheel"],
              ["/tmp/edgepii-wheel/bin/python","-c",
               "import pathlib,subprocess,sys; wheels=list(pathlib.Path('/tmp/edgepii-validation').glob('*.whl')); assert len(wheels)==1; subprocess.check_call([sys.executable,'-m','pip','install','--no-index','--no-deps','--force-reinstall',str(wheels[0])])"],
              ["/tmp/edgepii-wheel/bin/python","-I","-c",wheel_smoke],
              [sys.executable,"site/gen_data.py"],
              [sys.executable,"site/icons.py"],
              [sys.executable,"site/social.py"],
              [sys.executable,"site/build.py"],
              [sys.executable,"site/images.py"],
              [sys.executable,"site/check.py"],
              [sys.executable,"modal/check_evidence.py"],
              [sys.executable,"-m","pytest","tests","-o","addopts=","-q","-ra",f"--junitxml={artifacts/'junit.xml'}"]]
    if site_only:
        # Recheck final evidence links after the full-suite report is saved.
        # This mode is explicitly labeled and never substitutes for that run.
        site_commands = [c for c in commands if c[1].startswith(("site/", "modal/check_evidence.py"))]
        commands = [commands[0], *site_commands,
                    [sys.executable,"-m","pytest","tests/test_site.py","tests/test_site_e2e.py",
                     "-o","addopts=","-q","-ra",f"--junitxml={artifacts/'junit.xml'}"]]
    for command in commands:
        result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=1200)
        steps.append({"command":command,"exit_code":result.returncode,"output":(result.stdout+result.stderr)[-16000:]})
        print("Validation step:",command,"exit",result.returncode,flush=True)
        if result.returncode:
            print(steps[-1]["output"],flush=True)
            break
    summary={}
    if (artifacts/"junit.xml").exists():
        suite=ET.parse(artifacts/"junit.xml").getroot().find("testsuite")
        if suite is not None:summary=dict(suite.attrib)
    return {"mode":"site-only" if site_only else "full", "passed":all(row["exit_code"]==0 for row in steps),"steps":steps,"pytest":summary,
            "source_sha256":source_hashes,
            "wheel_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts.glob("*.whl")},
            "runtime":{"python":sys.version,"packages":dict(sorted((d.metadata["Name"],d.version) for d in importlib.metadata.distributions() if d.metadata["Name"]))},
            "files":{path.name:path.read_bytes() for path in artifacts.iterdir() if path.suffix in {".xml",".png"}}}


@app.local_entrypoint()
def main(out: str="docs/eval/validation", run_id: str="", site_only: bool=False):
    from uuid import uuid4
    import re
    if run_id and not re.fullmatch(r"[a-zA-Z0-9-]{1,64}",run_id):
        raise ValueError("run_id must contain at most 64 letters, digits, or hyphens")
    destination=Path(out)/(run_id or uuid4().hex[:8])
    destination.mkdir(parents=True,exist_ok=False)
    result=validate.remote(site_only)
    for name,body in result.pop("files").items():
        (destination/name).write_bytes(body)
    (destination/"validation.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("Validation",result["passed"],result["pytest"],destination)
    if not result["passed"]:
        raise SystemExit("Modal validation failed; inspect the saved evidence")
