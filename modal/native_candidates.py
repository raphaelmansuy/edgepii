"""Pinned native-label experiments; custom model code is verified before import."""

from pathlib import Path
import hashlib
import importlib.util
import sys

from edgepii.protocol import Hit
from edgepii.windows import checked_windows

TRACER_REVISION = "d25c16f2e57e321f6d2527715c01df9112f956f5"
TRACER_CODE_SHA256 = "c43724b9ac105a9b74d44aea7565e4c43ddc9d203f519324baa342be01269869"
MINILM_REVISION = "e5f6a01d465c9a2489a74a95ff1151359b759213"


def verified_module(path):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != TRACER_CODE_SHA256:
        raise ValueError("PII-Tracer custom code does not match the reviewed hash")
    name = "edgepii_reviewed_pii_masking"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class NativeTracer:
    revision = TRACER_REVISION
    preset_name = "tracer-native"

    def __init__(self, device="cuda", model=None, tokenizer=None):
        self.device = device
        if model is None:
            import torch
            from huggingface_hub import snapshot_download
            from transformers import AutoTokenizer
            snapshot = snapshot_download("perplexity-ai/PII-Tracer", revision=self.revision,
                allow_patterns=["*.json", "*.safetensors", "modeling_pii_masking.py"])
            module = verified_module(Path(snapshot)/"modeling_pii_masking.py")
            config = module.PiiMaskingConfig.from_pretrained(snapshot, local_files_only=True)
            model = module.PiiMaskingModel.from_pretrained(snapshot, config=config,
                dtype=torch.float16 if device.startswith("cuda") else torch.float32,
                attn_implementation="sdpa", local_files_only=True).to(device).eval()
            tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True,
                                                      trust_remote_code=False)
        self.model, self.tokenizer = model, tokenizer

    def locate(self, source):
        def count(text):
            return len(self.tokenizer(text, truncation=False)["input_ids"])
        hits = {}
        budget = int(self.model.config.max_seq_len)
        for start, end in checked_windows(source, count, budget):
            text = source[start:end]
            # The reviewed native helper truncates at this same budget. Every
            # complete input was checked above, so it cannot discard a tail.
            spans, _sensitivity = self.model.predict(text, tokenizer=self.tokenizer, max_length=budget)
            for span in spans:
                if not 0 <= span.start < span.end <= len(text):
                    raise ValueError("PII-Tracer returned invalid source offsets")
                a, b = start + span.start, start + span.end
                key = (span.label, a, b)
                hits[key] = Hit(span.label, a, b, None, "tracer.native", source[a:b])
        return tuple(hits[k] for k in sorted(hits))


class NativeMiniLM:
    revision = MINILM_REVISION
    preset_name = "minilm-native"

    def __init__(self, device="cuda", detector=None):
        self.device = device
        if detector is None:
            from edgepii.detectors.hf_token import HfTokenDetector
            detector = HfTokenDetector("crp4222/privaite-pii-minilm", self.revision, device)
        self.detector = detector

    def locate(self, source):
        hits = {}
        for hit in self.detector.locate(source, []):
            if (not 0 <= hit.start < hit.end <= len(source) or
                (hit.claimed_text is not None and hit.claimed_text != source[hit.start:hit.end])):
                raise ValueError("MiniLM returned invalid source offsets")
            key = (hit.raw_label, hit.start, hit.end)
            hits[key] = Hit(hit.raw_label, hit.start, hit.end, None,
                            "minilm.native", source[hit.start:hit.end])
        return tuple(hits[k] for k in sorted(hits))
