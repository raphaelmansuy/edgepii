"""Counterfactual stage audit; only counts and coverage flags leave the worker."""

from collections import Counter
from pathlib import Path
import hashlib
import json

from edgepii import Locator, protection_plan, redact_protected, restore
from edgepii.check import slice_text
from edgepii.eval.coverage import character_counts, covered, union_ranges
from edgepii.locator import _run_detector, _trim_edges
from edgepii.normalize import fold
from edgepii.protocol import coerce_hit


def audit_document(source, gold, detector, taxonomy):
    """Reuse each original/folded inference across all downstream stages."""
    allowed=set(taxonomy.default_types())
    high=[taxonomy.require(kind).class_name in {"secret","gov_id","payment"} for kind,_,_ in gold]
    cache={}
    class Replay:
        def locate(self,text,labels):
            if text not in cache:
                cache[text]=tuple(detector.locate(text,labels))
            return cache[text]
    replay=Replay()
    locator=Locator.from_detectors([replay],taxonomy=taxonomy.version)
    output={"gold_types":[kind for kind,_,_ in gold],"high_severity_gold":high,
            "branches":{},"inference_inputs":0}
    for name,normalized in (("original",None),("folded",fold(source))):
        text=source if normalized is None else normalized.text
        raw=[]
        trimmed=[]
        invalid=0
        labels=taxonomy.raw_labels_for(sorted(allowed))
        for item in replay.locate(text,labels):
            hit=coerce_hit(item)
            value=slice_text(text,hit)
            if value is None:
                invalid+=1
                continue
            raw.append((hit.raw_label,hit.start,hit.end))
            value,tidy=_trim_edges(text,hit,value)
            if value is not None:
                trimmed.append((tidy.raw_label,tidy.start,tidy.end))
        mapped,dropped,unknown=_run_detector(replay,text,labels,taxonomy)
        unknown_labels=Counter(coerce_hit(h).raw_label for h in replay.locate(text,labels)
                               if taxonomy.public_type(coerce_hit(h).raw_label) is None)
        def to_source(rows):
            out=[]
            for kind,a,b in rows:
                if normalized is not None and normalized.changed:
                    a,b=normalized.to_source(a,b)
                if not 0 <= a < b <= len(source):
                    raise ValueError("invalid audited original-source range")
                out.append((kind,a,b))
            return out
        result=locator.locate(source,fold=False if normalized is None else "confusables")
        assert result.dropped==dropped
        assert all(source[s.start:s.end]==s.text for s in result._candidates)
        plan=protection_plan(source,result._candidates,taxonomy=taxonomy,
                            dropped=result.dropped,unmapped=result.unmapped,strict=False)
        masked,vault=redact_protected(source,plan)
        for a,b in plan._secret_ranges:
            assert not any(source[a:b] in value for value in vault.values())
        if not any(s.irreversible for s in plan.segments):
            assert restore(masked,vault).text==source
        stages={"raw_native":to_source(raw),"trimmed_native":to_source(trimmed),
                "mapped_public":to_source([(s.type,s.start,s.end) for s in mapped]),
                "eligible_candidates":[(s.type,s.start,s.end) for s in result._candidates if s.type in allowed],
                "selected":[(s.type,s.start,s.end) for s in result.spans],
                "protected":[("PROTECTED",s.start,s.end) for s in plan.segments]}
        metrics={}
        for stage,rows in stages.items():
            ranges=union_ranges((a,b) for _,a,b in rows)
            gc,mc,cc=character_counts(gold,rows)
            metrics[stage]={"covered":[covered(a,b,ranges) for _,a,b in gold],
                "gold_characters":gc,"masked_characters":mc,"covered_characters":cc}
        losses={}
        for before,after in (("raw_native","trimmed_native"),("trimmed_native","mapped_public"),
                             ("mapped_public","eligible_candidates"),("eligible_candidates","selected")):
            losses[before+"->"+after]={"gold_spans":sum(a and not b for a,b in zip(metrics[before]["covered"],metrics[after]["covered"])),
                "high_severity":sum(h and a and not b for h,a,b in zip(high,metrics[before]["covered"],metrics[after]["covered"]))}
        output["branches"][name]={"stages":metrics,"losses":losses,
            "dropped_offsets":invalid,"unmapped_predictions":unknown,
            "unmapped_labels":dict(sorted(unknown_labels.items()))}
    output["inference_inputs"]=len(cache)
    return output


def summarize(cases):
    if not cases:
        raise ValueError("stage audit requires non-empty cases")
    summary={}
    for branch in ("original","folded"):
        stages={}
        for name in cases[0]["branches"][branch]["stages"]:
            rows=[c["branches"][branch]["stages"][name] for c in cases]
            contained=sum(sum(r["covered"]) for r in rows)
            missed=sum(sum(h and not hit for h,hit in zip(c["high_severity_gold"],r["covered"])) for c,r in zip(cases,rows))
            stages[name]={"contained_gold":contained,"high_severity_misses":missed,
                "masked_characters":sum(r["masked_characters"] for r in rows),
                "covered_characters":sum(r["covered_characters"] for r in rows)}
        labels=Counter()
        for c in cases:labels.update(c["branches"][branch]["unmapped_labels"])
        summary[branch]={"stages":stages,"unmapped_predictions":sum(c["branches"][branch]["unmapped_predictions"] for c in cases),
                         "unmapped_labels":dict(sorted(labels.items()))}
    return {"documents":len(cases),"gold_spans":sum(len(c["gold_types"]) for c in cases),
            "high_severity_gold":sum(sum(c["high_severity_gold"]) for c in cases),"branches":summary}


def run_audit(locator,corpus,limit):
    from edgepii.eval.corpora import load_spec,ensure_file,read_raw,materialize_spy,build_docs
    from edgepii.eval.runner import _slice_membership,_selected_docs,SPY_SEED,SPY_PROTOCOL
    taxonomy=locator.taxonomy
    spec=load_spec(corpus)
    records=read_raw(ensure_file(spec,Path("/cache/corpora")))
    if spec.spans_encoding=="bio":
        records=materialize_spy(records,seed=SPY_SEED,protocol=SPY_PROTOCOL)
    docs,diagnostics=build_docs(records,spec,set(taxonomy.default_types()))
    assert not diagnostics.unknown and diagnostics.bad_offset==0 and diagnostics.text_mismatch==0
    selected=_selected_docs(_slice_membership(spec,["all",*sorted(spec.slices)],docs),limit)
    digest=hashlib.sha256()
    cases=[]
    for index,doc in enumerate(docs):
        if index not in selected:continue
        digest.update(json.dumps([index,doc.doc_id,doc.text,doc.spans,sorted(selected[index])],ensure_ascii=False,separators=(",",":")).encode())
        cases.append(audit_document(doc.text,doc.spans,locator.detectors[-1],taxonomy))
    return {"mode":"counterfactual-stage-audit","provider":"modal","corpus":corpus,
            "preset":locator.preset_name,"revision":locator.revision,"selection_sha256":digest.hexdigest(),
            "summary":summarize(cases),"cases":cases,
            "scope":"model-only source-free diagnostics; strict=False protection is not deployment readiness",
            "stage_helper_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
