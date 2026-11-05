"""Native-label OPF experiment. This is deliberately not a public typed preset."""

from types import SimpleNamespace
from pathlib import Path

from edgepii.protocol import Hit

OPF_REVISION = "7ffa9a043d54d1be65afb281eddf0ffbe629385b"
OPF_SOURCE = "f7f00ca7fb869683eb732c010299d901457f19c3"


class NativeOpf:
    def __init__(self, device="cuda", runner=None):
        self.device = device
        if runner is None:
            from huggingface_hub import snapshot_download
            from opf import OPF

            snapshot = snapshot_download("openai/privacy-filter", revision=OPF_REVISION,
                                         allow_patterns=["original/*.json", "original/*.safetensors"])
            # Root files are the Transformers conversion. The native runtime
            # requires the original architecture config and weight names.
            runner = OPF(model=str(Path(snapshot) / "original"), device=device, decode_mode="viterbi",
                         context_window_length=4096)
        self.runner = runner

    def locate(self, source: str):
        result = self.runner.redact(source)
        if result.warning or result.text != source or result.summary.get("decoded_mismatch"):
            raise ValueError("OPF tokenizer did not preserve the original source")
        hits = []
        for span in result.detected_spans:
            if not (0 <= span.start < span.end <= len(source)) or source[span.start:span.end] != span.text:
                raise ValueError("OPF returned an invalid original-source span")
            hits.append(Hit(span.label, span.start, span.end, None, "opf.native", span.text))
        return tuple(hits)


class NativeEvaluationLocator:
    """Only for the corpus harness; native labels are never public taxonomy types."""
    preset_name = "opf-native"
    revision = OPF_REVISION

    def __init__(self, detector):
        from edgepii.labelmap import load_taxonomy
        self.taxonomy = load_taxonomy()
        self.detectors = (detector,)

    def locate(self, source, **kwargs):
        hits = self.detectors[0].locate(source)
        return SimpleNamespace(dropped=0, spans=[SimpleNamespace(
            type=hit.raw_label, start=hit.start, end=hit.end, text=hit.claimed_text
        ) for hit in hits])


def native_report(detector, corpus, cache, limit):
    from edgepii.eval.runner import score_corpus
    report = score_corpus(NativeEvaluationLocator(detector), corpus, cache, limit=limit).to_dict()
    report["evaluation"]["mode"] = "native-label containment; no public taxonomy projection"
    report["evaluation"]["decoder_source_revision"] = OPF_SOURCE
    for row in report["slices"].values():
        for key in ("tp", "fp", "fn", "precision", "recall", "f1", "f2",
                    "miss", "wrong_type", "shift", "extra", "per_type"):
            row.pop(key, None)
    return report
