"""Model runtime regressions without downloading weights or importing torch."""

import sys
from types import SimpleNamespace

import pytest

from edgepii import DetectorLoadError, Locator
from edgepii.detectors.gliner import GlinerDetector
from edgepii.detectors.gliner2 import Gliner2Detector
from edgepii.detectors.hf_token import HfTokenDetector


class FakeModel:
    def __init__(self):
        self.device = None
        self.evaluating = False
        self.encoder = SimpleNamespace(config=SimpleNamespace(max_position_embeddings=512))
        self.processor = SimpleNamespace(transform_record=lambda text, schema, **k: SimpleNamespace(input_ids=list(text)))

    def create_schema(self):
        return SimpleNamespace(entities=lambda labels: labels)

    def to(self, device):
        self.device = device
        return self

    def eval(self):
        self.evaluating = True


def test_gliner2_pins_the_entire_snapshot_and_uses_requested_device(monkeypatch):
    model = FakeModel()
    calls = []

    def download(repo, **kwargs):
        calls.append((repo, kwargs))
        return "/pinned/snapshot"

    def load(path):
        assert path == "/pinned/snapshot"
        return model

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    monkeypatch.setitem(sys.modules, "gliner2", SimpleNamespace(AutoExtractor=SimpleNamespace(from_pretrained=load)))
    Gliner2Detector("model/repo", "commit-sha", device="cuda:1")
    assert calls == [("model/repo", {"revision": "commit-sha"})]
    assert model.device == "cuda:1"
    assert model.evaluating


@pytest.mark.parametrize("adapter,module,model_name", [
    (GlinerDetector, "gliner", "GLiNER"),
    (Gliner2Detector, "gliner2", "AutoExtractor"),
])
def test_a_load_typeerror_never_retries_with_floating_weights(monkeypatch, adapter, module, model_name):
    calls = []

    def load(*args, **kwargs):
        calls.append((args, kwargs))
        raise TypeError("incompatible runtime")

    monkeypatch.setitem(sys.modules, module, SimpleNamespace(**{model_name: SimpleNamespace(from_pretrained=load)}))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=lambda *a, **k: "/pin"))
    with pytest.raises(DetectorLoadError, match="revision=commit-sha"):
        adapter("model/repo", "commit-sha")
    assert len(calls) == 1


def test_gliner_moves_to_gpu_and_evaluates(monkeypatch):
    model = FakeModel()
    calls = []

    def load(repo, **kwargs):
        calls.append((repo, kwargs))
        return model

    monkeypatch.setitem(sys.modules, "gliner", SimpleNamespace(GLiNER=SimpleNamespace(from_pretrained=load)))
    GlinerDetector("model/repo", "sha", device="cuda")
    assert calls == [("model/repo", {"revision": "sha"})]
    assert model.device == "cuda"
    assert model.evaluating


@pytest.mark.parametrize("device", ["cpu", "cuda", "cuda:1", "mps"])
def test_hf_preserves_the_requested_device(monkeypatch, device):
    def pipeline(*args, **kwargs):
        assert kwargs["device"] == device
        return SimpleNamespace(model=SimpleNamespace(config=SimpleNamespace(max_position_embeddings=512)))

    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(pipeline=pipeline))
    HfTokenDetector("model/repo", "sha", device=device)


def test_gliner2_rejects_a_reported_surface_that_disagrees_with_offsets():
    detector = Gliner2Detector.__new__(Gliner2Detector)
    detector.repo_id = "test"
    detector.candidate_floor = None
    detector._model = FakeModel()
    detector._model.extract_entities=lambda *a, **k: {
        "entities": {"person": [{"start": 0, "end": 3, "text": "Bob", "confidence": 0.9}]}
    }
    result = Locator.from_detectors([detector]).locate("Ada", types=["PERSON"])
    assert result.spans == ()
    assert result.dropped == 1
