"""Evaluation-only compact models with pinned artifacts and explicit decoding."""

from edgepii.protocol import Hit
from edgepii.windows import checked_windows

MASKER_REPO = "divergentlabs/masker-mini"
MASKER_REVISION = "beb7235d454aa4488b6ee1cd47f417caa12a6d15"
ETTIN_REVISION = "84ce02cac78d9cee27a125629ba195f12c75fe5b"
HORIZON_REVISION = "a20835db9e671267b21a2951f5bf2c76e4901708"


def decode_bioes(source, offsets, labels):
    """Argmax BIOES decoding; orphan I/E starts a span, matching type extends it.

    Special/zero-width tokens close a span. Invalid ranges fail. Labels never
    become public taxonomy types, and no source search repairs an offset.
    """
    if len(offsets) != len(labels):
        raise ValueError("token/label length mismatch")
    spans = []
    active = None

    def close():
        nonlocal active
        if active is not None:
            label, a, b = active
            spans.append(Hit(label, a, b, None, "masker.native", source[a:b]))
            active = None

    for (a, b), label in zip(offsets, labels):
        a, b = int(a), int(b)
        if not 0 <= a <= b <= len(source):
            raise ValueError("invalid token source offsets")
        if a == b or label == "O":
            close()
            continue
        if len(label) < 3 or label[0] not in "BIES" or label[1] != "-":
            raise ValueError("unsupported BIOES label")
        prefix, kind = label[0], label[2:]
        if prefix in "BS" or active is None or active[0] != kind:
            close()
            active = (kind, a, b)
        else:
            if a < active[1]:
                raise ValueError("nonmonotone token source offsets")
            active = (kind, active[1], max(active[2], b))
        if prefix in "ES":
            close()
    close()
    return tuple(spans)


class NativeMasker:
    revision = MASKER_REVISION
    preset_name = "masker-mini-native"
    backend = "torch-fp32"
    decoder = "token argmax; BIOES v1, orphan I/E starts span"

    def __init__(self, device="cuda"):
        import json
        from pathlib import Path
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer
        self.device = device
        patterns = ["*.json", "spm.model"]
        patterns += ["onnx/model_int4.onnx"] if self.backend == "onnx-int4" else ["model.safetensors"]
        snapshot = snapshot_download(MASKER_REPO, revision=self.revision, allow_patterns=patterns)
        config = json.loads((Path(snapshot)/"config.json").read_text())
        self.labels = {int(k): v for k, v in config["id2label"].items()}
        self.token_budget = config["max_position_embeddings"]
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True,
                                                       trust_remote_code=False)
        if not self.tokenizer.is_fast:
            raise ValueError("original offsets require a fast tokenizer")
        if self.backend == "onnx-int4":
            if device != "cpu":
                raise ValueError("quantized control requires CPU")
            import onnxruntime as ort
            options = ort.SessionOptions()
            options.intra_op_num_threads = 4
            options.inter_op_num_threads = 1
            self.session = ort.InferenceSession(str(Path(snapshot)/"onnx/model_int4.onnx"),
                sess_options=options, providers=["CPUExecutionProvider"])
        else:
            import torch
            from transformers import AutoModelForTokenClassification
            self.model = AutoModelForTokenClassification.from_pretrained(snapshot,
                local_files_only=True, trust_remote_code=False, dtype=torch.float32).to(device).eval()

    def locate(self, source):
        def count(text):
            return len(self.tokenizer(text, truncation=False, add_special_tokens=True)["input_ids"])
        hits = {}
        for start, end in checked_windows(source, count, self.token_budget):
            text = source[start:end]
            encoded = self.tokenizer(text, return_offsets_mapping=True,
                truncation=False, return_tensors="np" if self.backend == "onnx-int4" else "pt")
            offsets = encoded.pop("offset_mapping")[0].tolist()
            assert len(encoded["input_ids"][0]) <= self.token_budget
            if self.backend == "onnx-int4":
                import numpy as np
                feed = {row.name: encoded[row.name].astype(np.int64) for row in self.session.get_inputs()}
                ids = self.session.run(None, feed)[0][0].argmax(axis=-1).tolist()
            else:
                import torch
                with torch.inference_mode():
                    ids = self.model(**{k: v.to(self.device) for k, v in encoded.items()}).logits[0].argmax(-1).cpu().tolist()
            for hit in decode_bioes(text, offsets, [self.labels[i] for i in ids]):
                a, b = start + hit.start, start + hit.end
                hits[(hit.raw_label, a, b)] = Hit(hit.raw_label, a, b, None,
                    self.preset_name, source[a:b])
        return tuple(hits[key] for key in sorted(hits))


class NativeMaskerInt4(NativeMasker):
    preset_name = "masker-int4-native"
    backend = "onnx-int4"


def build_compact(name, device):
    if name in {"masker-mini-native", "masker-int4-native"}:
        return (NativeMasker if name == "masker-mini-native" else NativeMaskerInt4)(device)
    from native_candidates import NativeMiniLM
    from edgepii.detectors.hf_token import HfTokenDetector
    repo, revision = {
        "ettin-native": ("kalyan-ks/ettin-32m-nemotron-pii", ETTIN_REVISION),
        "horizon-native": ("Horizon-Labs/pii-redactor-small", HORIZON_REVISION),
    }[name]
    detector = NativeMiniLM(device, detector=HfTokenDetector(repo, revision, device))
    detector.revision, detector.preset_name = revision, name
    detector.backend = "transformers-pipeline-" + str(detector.detector._pipe.model.dtype)
    detector.decoder = "Transformers aggregation_strategy=simple; native labels"
    return detector
