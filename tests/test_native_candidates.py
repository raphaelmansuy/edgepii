"""Native model contracts without dependencies or floating remote code."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from edgepii.protocol import Hit

spec = importlib.util.spec_from_file_location("edgepii_native_candidates_test",
                                             Path(__file__).parents[1]/"modal/native_candidates.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def test_unreviewed_custom_code_is_rejected_before_execution(tmp_path):
    code = tmp_path/"model.py"
    code.write_text("raise RuntimeError('executed unreviewed code')")
    with pytest.raises(ValueError,match="reviewed hash"):
        native.verified_module(code)


def test_native_tracer_checks_dense_unicode_tail_and_ignores_sensitivity_gate():
    source = "中" * 113 + "ada@example.com"
    class Tokenizer:
        def __call__(self,text,**kwargs):
            return {"input_ids":[0]*(2+sum(4 if ord(c)>127 else 1 for c in text))}
    tokenizer = Tokenizer()
    calls=[]
    class Model:
        config=SimpleNamespace(max_seq_len=64)
        def predict(self,text,tokenizer,max_length):
            assert len(tokenizer(text)["input_ids"]) <= max_length
            calls.append(text)
            start=text.find("ada@example.com")
            spans=[] if start<0 else [SimpleNamespace(label="private_email",start=start,end=start+15)]
            return spans,0.0  # A low document score must never suppress spans.
    detector=native.NativeTracer(model=Model(),tokenizer=tokenizer)
    hits=detector.locate(source)
    assert len(calls)>1
    assert [(h.start,h.end,h.claimed_text) for h in hits] == [(113,128,"ada@example.com")]


def test_native_tracer_rejects_invalid_offsets():
    model=SimpleNamespace(config=SimpleNamespace(max_seq_len=64),
        predict=lambda *a,**k:([SimpleNamespace(label="private_person",start=-1,end=3)],1.))
    with pytest.raises(ValueError,match="invalid source offsets"):
        native.NativeTracer(model=model,tokenizer=lambda text,**k:{"input_ids":[1]}).locate("Ada")


def test_minilm_keeps_coarse_native_categories_and_deduplicates_windows():
    hit=Hit("CONTACT",0,15,.9,"model")
    detector=native.NativeMiniLM(detector=SimpleNamespace(locate=lambda *a:[hit,hit]))
    assert [h.raw_label for h in detector.locate("ada@example.com")] == ["CONTACT"]


def test_minilm_rejects_a_disagreeing_claimed_surface():
    hit=Hit("PERSON",0,3,.9,"model","Bob")
    detector=native.NativeMiniLM(detector=SimpleNamespace(locate=lambda *a:[hit]))
    with pytest.raises(ValueError,match="invalid source offsets"):detector.locate("Ada")
