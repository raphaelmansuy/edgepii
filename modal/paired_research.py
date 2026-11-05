"""Paired comparison worker, invoked through models.py --paired.

This module has no Modal resource definitions; the established Model class
owns the image, Volume, credentials, and hardware configuration.
"""

import json
from pathlib import Path

def run_experiment(corpus: str, limit: int, quantized: bool):
    import hashlib
    import importlib.metadata
    import time
    import torch
    from compact_candidates import build_compact
    from native_candidates import NativeTracer
    from paired_metrics import case_metrics, summarize
    from edgepii.labelmap import load_taxonomy
    from edgepii.eval.corpora import load_spec, ensure_file, read_raw, materialize_spy, build_docs
    from edgepii.eval.runner import _slice_membership, _selected_docs, SPY_SEED, SPY_PROTOCOL, HIGH_SEVERITY

    torch.set_num_threads(4)
    device = "cpu" if quantized else "cuda"
    names = (["masker-mini-native","masker-int4-native"] if quantized else
             ["masker-mini-native","ettin-native","horizon-native","tracer-native"])
    models = {name: (NativeTracer(device) if name == "tracer-native" else build_compact(name,device)) for name in names}
    for model in models.values():
        model.locate("Contact Ada at ada@example.com.")
    taxonomy=load_taxonomy()
    allowed=set(taxonomy.default_types())
    high_types={name for name in allowed if taxonomy.types[name].class_name in HIGH_SEVERITY}
    spec=load_spec(corpus)
    records=read_raw(ensure_file(spec,Path("/cache/corpora")))
    if spec.spans_encoding == "bio":
        records=materialize_spy(records,seed=SPY_SEED,protocol=SPY_PROTOCOL)
    docs,diagnostics=build_docs(records,spec,allowed)
    assert not diagnostics.unknown and diagnostics.bad_offset == 0 and diagnostics.text_mismatch == 0
    selected=_selected_docs(_slice_membership(spec,["all",*sorted(spec.slices)],docs),limit)
    selection=hashlib.sha256()
    cases=[]
    support={name:{} for name in names}
    milliseconds={name:[] for name in names}
    for index,doc in enumerate(docs):
        if index not in selected:
            continue
        selection.update(json.dumps([index,doc.doc_id,doc.text,doc.spans,sorted(selected[index])],ensure_ascii=False,separators=(",",":")).encode())
        predictions={}
        for name,model in models.items():
            started=time.perf_counter()
            hits=model.locate(doc.text)
            milliseconds[name].append((time.perf_counter()-started)*1000)
            assert all(0 <= h.start < h.end <= len(doc.text) and h.claimed_text == doc.text[h.start:h.end] for h in hits)
            predictions[name]=[(h.raw_label,h.start,h.end) for h in hits]
            for gold_type,a,b in doc.spans:
                for hit in hits:
                    if hit.start <= a and hit.end >= b:
                        key=gold_type+" <- "+hit.raw_label+" -> "+str(taxonomy.public_type(hit.raw_label))
                        support[name][key]=support[name].get(key,0)+1
        cases.append(case_metrics(doc.spans,predictions,high_types))
    return {"mode":"paired-native-range-research","provider":"modal","corpus":corpus,
        "limit_per_slice":limit,"selection_sha256":selection.hexdigest(),
        "materialization_protocol":SPY_PROTOCOL if spec.spans_encoding=="bio" else "source-v1",
        "device":device,"gpu":torch.cuda.get_device_name(0) if device=="cuda" else None,
        "cpu_threads":torch.get_num_threads(),"quantized":quantized,
        "models":{name:{"revision":m.revision,"backend":getattr(m,"backend","native-pii-tracer")} for name,m in models.items()},
        "summary":summarize(cases),"cases":cases,"locate_ms":milliseconds,
        "single_span_support_counts":support,
        "support_scope":"gold-type <- native-label -> existing global taxonomy mapping; counts qualifying predictions, not unique gold",
        "scope":"native range union, no public type projection or irreversible protection plan; public prefix exploration, no trained routing policy",
        "helper_sha256":{f:hashlib.sha256(Path('/root',f).read_bytes()).hexdigest() for f in ("compact_candidates.py","native_candidates.py","paired_metrics.py")},
        "packages":dict(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions() if d.metadata['Name']))}
