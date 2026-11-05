"""Counterfactual stage losses have independent, hand-calculated examples."""

import importlib.util
import json
from pathlib import Path

from edgepii.labelmap import load_taxonomy
from edgepii.protocol import Hit

spec=importlib.util.spec_from_file_location("stage_audit_test",Path(__file__).parents[1]/"modal/stage_audit.py")
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_unmapped_identifier_is_attributed_to_projection_without_reinference():
    calls=[]
    class Detector:
        def locate(self,text,labels):
            calls.append(text)
            return [Hit("MEDICAL_ID",0,len(text),.9,"model")]
    source="123-45-6789"
    case=audit.audit_document(source,[("GOV_ID",0,len(source))],Detector(),load_taxonomy())
    assert calls==[source]
    branch=case["branches"]["original"]
    assert branch["losses"]["trimmed_native->mapped_public"]["high_severity"]==1
    assert branch["stages"]["raw_native"]["covered"]==[True]
    assert branch["stages"]["protected"]["covered"]==[False]
    assert branch["unmapped_predictions"]==1
    assert source not in json.dumps(case)


def test_trimming_opens_a_space_between_fragments_without_losing_letters():
    class Detector:
        def locate(self,text,labels):
            return [Hit("PERSON",0,4,.9,"model"),Hit("PERSON",4,12,.9,"model")]
    case=audit.audit_document("Ada Lovelace",[("PERSON",0,12)],Detector(),load_taxonomy())
    branch=case["branches"]["original"]
    assert branch["losses"]["raw_native->trimmed_native"]["gold_spans"]==1
    assert branch["stages"]["trimmed_native"]["covered_characters"]==11
    assert branch["stages"]["raw_native"]["covered_characters"]==12


def test_folded_counterfactual_maps_back_to_original_unicode():
    calls=[]
    class Detector:
        def locate(self,text,labels):
            calls.append(text)
            return [Hit("EMAIL",0,len(text),.9,"model")] if text=="ada@example.com" else []
    source="ａｄａ＠ｅｘａｍｐｌｅ．ｃｏｍ"
    case=audit.audit_document(source,[("EMAIL",0,len(source))],Detector(),load_taxonomy())
    assert len(calls)==2
    assert case["branches"]["original"]["stages"]["protected"]["covered"]==[False]
    assert case["branches"]["folded"]["stages"]["protected"]["covered"]==[True]
