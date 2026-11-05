"""Private, reusable inference and matched-corpus evaluation on Modal.

Run: .venv/bin/modal run modal/models.py --corpus spy-legal --limit 200
Deploy for SDK inference: .venv/bin/modal deploy modal/models.py
"""

from pathlib import Path
import json
import os
import subprocess

import modal

ROOT = Path(__file__).resolve().parents[1]
app = modal.App("edgepii-models")
cache = modal.Volume.from_name("edgepii-model-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.8.0", "transformers==5.22.1", "gliner2[local]==2.1.0",
        "peft==0.21.2", "sentencepiece==0.2.1", "phonenumbers==9.0.42",
        # Arrow 26 imports require NumPy 2 despite missing Requires-Dist
        # metadata. Keep the tested NumPy 1 runtime and compatible reader.
        "numpy==1.26.4", "pyyaml==6.0.3", "pyarrow==20.0.0", "faker==40.44.0",
    )
    # Modal's base includes FastAPI; keep it compatible with GLiNER2's Pydantic.
    .pip_install("fastapi==0.162.0")
    .pip_install("https://github.com/openai/privacy-filter/archive/f7f00ca7fb869683eb732c010299d901457f19c3.zip")
    .run_commands("python -c 'import numpy; import pyarrow.parquet; print(\"Parquet import preflight passed\", numpy.__version__)'",
                  "python -m pip check")
    .env({"HF_HOME": "/cache/huggingface", "EDGEPII_LOG_TEXT": "0",
          "TOKENIZERS_PARALLELISM": "false"})
    .add_local_dir(ROOT / "src", "/opt/edgepii/src", copy=True,
                   ignore=["**/__pycache__/**", "**/*.pyc"])
    .add_local_file(ROOT / "pyproject.toml", "/opt/edgepii/pyproject.toml", copy=True)
    .add_local_file(ROOT / "README.md", "/opt/edgepii/README.md", copy=True)
    .add_local_file(ROOT / "LICENSE", "/opt/edgepii/LICENSE", copy=True)
    .add_local_file(ROOT / "modal" / "native_opf.py", "/root/native_opf.py", copy=True)
    .run_commands("pip install --no-deps /opt/edgepii")
)
# Public checkpoints need no token. A gated model can use an explicitly supplied
# HF_TOKEN without making authentication a requirement for the public lanes.
secrets = [modal.Secret.from_local_environ(["HF_TOKEN"])] if os.getenv("HF_TOKEN") else []
SUPPORTED = {"rules", "en-closed", "multi-open", "multi-encoder", "multi-boundary", "opf-native"}


@app.cls(image=image, cpu=4, memory=16384, volumes={"/cache": cache},
         secrets=secrets, timeout=1800, startup_timeout=300,
         max_containers=1, scaledown_window=60)
class Model:
    preset: str = modal.parameter(default="en-closed")
    device: str = modal.parameter(default="cpu")

    @modal.enter()
    def load(self):
        import time
        import torch
        from edgepii import Locator

        if self.preset not in SUPPORTED:
            raise ValueError("unsupported Modal model preset")
        torch.set_num_threads(4)
        print(f"Loading preset={self.preset} device={self.device}", flush=True)
        started = time.perf_counter()
        if self.preset == "opf-native":
            from native_opf import NativeOpf
            self.native = NativeOpf(self.device)
            self.native.locate("Contact Ada Lovelace at ada@example.com.")
        else:
            self.locator = Locator.preset(self.preset, device=self.device)
            self.locator.locate("Contact Ada Lovelace at ada@example.com.")
        self.load_seconds = time.perf_counter() - started
        # Warm up separately so evaluation latency excludes initialization.
        cache.commit()
        print(f"Ready preset={self.preset} load_seconds={self.load_seconds:.2f}", flush=True)

    @modal.method()
    def locate(self, source: str, types: list[str] | None = None) -> dict:
        """SDK-only method. Source and span text cross the Modal boundary."""
        if not isinstance(source, str) or len(source) > 100_000:
            raise ValueError("source must be a string of at most 100000 characters")
        if self.preset == "opf-native":
            raise ValueError("native OPF is an evaluation experiment, not a typed SDK preset")
        return self.locator.locate(source, types=types).to_dict()

    @modal.method()
    def verify(self) -> dict:
        """Exercise actual inference; report contracts separately from accuracy."""
        from edgepii import Locator, redact, restore
        cases = ["Contact Ada Lovelace at ada@example.com.",
                 "Email аda＠example.com and password hunter2.",
                 "中" * 3000 + " Email ada@example.com.",
                 "ada@example.com then ada@example.com",
                 "Order 48291 ships next Tuesday."]
        spans = 0
        model_spans = 0
        for index, source in enumerate(cases):
            if self.preset == "opf-native":
                hits = self.native.locate(source)
                spans += len(hits)
                model_spans += len(hits)
                continue
            result = self.locator.locate(source)
            assert result.dropped == 0, "model returned invalid offsets"
            assert all(source[s.start:s.end] == s.text for s in result.spans)
            masked, vault = redact(source, result.spans)
            assert "hunter2" not in str(vault)
            answer = restore(masked, vault)
            if not any(s.type == "SECRET" for s in result.spans):
                assert answer.text == source, "reversible spans did not round trip"
            spans += len(result.spans)
            if self.preset != "rules" and index == 0:
                direct = Locator.from_detectors([self.locator.detectors[-1]]).locate(source)
                model_spans += len(direct.spans)
        if self.preset != "rules":
            assert model_spans > 0, "rule-disabled model smoke returned no spans"
        return {"cases":len(cases),"valid_original_source_spans":spans,
                "model_only_smoke_spans":model_spans,"contract_passed":True,
                "scope":"inference and source/masking invariants; not an accuracy guarantee"}

    @modal.method()
    def evaluate(self, corpus: str, limit: int = 200) -> dict:
        import hashlib
        import importlib.metadata
        import torch
        from edgepii.eval.runner import score_corpus

        if not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        print(f"Evaluating preset={self.preset} corpus={corpus} limit={limit}", flush=True)
        if self.preset == "opf-native":
            from native_opf import native_report
            payload = native_report(self.native, corpus, Path("/cache/corpora"), limit)
        else:
            payload = score_corpus(self.locator, corpus, Path("/cache/corpora"), limit=limit).to_dict()
            if self.preset != "rules":
                from edgepii import Locator
                isolated = Locator.from_detectors([self.locator.detectors[-1]])
                ablation = score_corpus(isolated, corpus, Path("/cache/corpora"), limit=limit).to_dict()
                if ablation["evaluation"]["selection_sha256"] != payload["evaluation"]["selection_sha256"]:
                    raise RuntimeError("model-only ablation used different inputs")
                payload["model_only_ablation"] = ablation
        payload["runtime"] = {
            "provider": "modal", "device": self.device,
            "deployment_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "gpu": torch.cuda.get_device_name(0) if self.device.startswith("cuda") else None,
            "model_load_seconds": self.load_seconds,
            "model_load_scope": "download, initialization, and one warmup; excludes container startup",
            "warmup": "one synthetic document before timing",
            "installed_packages": dict(sorted(
                (dist.metadata["Name"], dist.version)
                for dist in importlib.metadata.distributions() if dist.metadata["Name"]
            )),
        }
        cache.commit()
        return payload


@app.local_entrypoint()
def main(corpus: str = "spy-legal", limit: int = 200,
         presets: str = "rules,en-closed,multi-open", gpu: str = "L4",
         out: str = "docs/eval/modal", min_recall: float = 0.0,
         max_leaks: int = -1):
    from edgepii.eval.corpora import load_spec
    from edgepii.eval.gates import GatePolicy, check_gates

    load_spec(corpus)  # validate before allocating compute
    names = list(dict.fromkeys(name.strip() for name in presets.split(",")))
    if not names or set(names) - SUPPORTED:
        raise ValueError(f"presets must be chosen from {sorted(SUPPORTED)}")
    if not 1 <= limit <= 10_000:
        raise ValueError("limit must be between 1 and 10000")
    policy = GatePolicy(min_recall=min_recall,
                        max_leaks=None if max_leaks == -1 else max_leaks)
    if "opf-native" in names and min_recall > 0:
        raise ValueError("native OPF uses containment metrics, not a typed recall floor")
    from uuid import uuid4
    destination = Path(out) / f"{corpus}-{limit}-{uuid4().hex[:8]}"
    destination.mkdir(parents=True, exist_ok=False)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    selection = None
    failed = False
    manifest = {"state":"running","requested_presets":names,"completed":[],"failures":[]}
    manifest_path = destination / "run.json"
    def save_manifest():
        manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    save_manifest()
    for name in names:
        use_gpu = name != "rules" and gpu != "cpu"
        options = {"gpu": gpu} if use_gpu else {}
        print(f"Starting preset={name} hardware={gpu if use_gpu else 'cpu'}", flush=True)
        model = Model.with_options(**options)(preset=name, device="cuda" if use_gpu else "cpu")
        try:
            verification = model.verify.remote()
            payload = model.evaluate.remote(corpus, limit)
            payload["first_principles_verification"] = verification
        except BaseException as exc:
            manifest["state"] = "failed"
            manifest["failures"].append({"preset":name,"error_type":type(exc).__name__})
            save_manifest()
            raise
        payload["code"] = {"git_revision": revision, "dirty": dirty}
        native = name == "opf-native"
        payload["gates"] = check_gates(payload, GatePolicy(max_leaks=policy.max_leaks)) if native else check_gates(payload, policy)
        digest = payload["evaluation"]["selection_sha256"]
        if selection is not None and selection != digest:
            raise RuntimeError("models were evaluated on different documents")
        selection = digest
        path = destination / f"{corpus}__{name}-{limit}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        manifest["completed"].append({"preset":name,"report":path.name,"gates_passed":payload["gates"]["passed"]})
        save_manifest()
        row = payload["slices"]["all"]
        quality = f"containment={row['containment']['span_recall']:.3f}" if native else f"recall={row['recall']:.3f} F2={row['f2']:.3f}"
        print(f"{name}: {quality} "
              f"leaks={row['high_severity_leaks']} p95={payload['latency_ms']['p95']:.1f}ms; {path}", flush=True)
        failed |= not payload["gates"]["passed"]
    manifest["state"] = "quality-gates-failed" if failed else "complete"
    save_manifest()
    if failed:
        raise SystemExit("evaluation gates failed; inspect the saved reports")
