"""Source-free paired coverage diagnostics for experimental native detectors."""

from itertools import combinations

from edgepii.eval.coverage import character_counts, covered, union_ranges


def case_metrics(gold, predictions, high_types):
    high = [kind in high_types for kind, _, _ in gold]
    models = {}
    for name, rows in sorted(predictions.items()):
        masks = union_ranges((a,b) for _,a,b in rows)
        gc, mc, cc = character_counts(gold, rows)
        models[name] = {"covered": [covered(a,b,masks) for _,a,b in gold],
                        "gold_characters":gc,"masked_characters":mc,"covered_characters":cc}
    pairs = {}
    for left, right in combinations(sorted(predictions), 2):
        combined = predictions[left] + predictions[right]
        masks = union_ranges((a,b) for _,a,b in combined)
        _, mc, cc = character_counts(gold, combined)
        pairs[left+"+"+right] = {
            "covered": [covered(a,b,masks) for _,a,b in gold],
            "masked_characters":mc,"covered_characters":cc,
            "range_parity": union_ranges((a,b) for _,a,b in predictions[left]) == union_ranges((a,b) for _,a,b in predictions[right]),
            "native_span_parity": set(predictions[left]) == set(predictions[right]),
        }
    return {"high_severity_gold":high, "models":models, "pairs":pairs}


def summarize(cases):
    if not cases:
        raise ValueError("paired research requires non-empty cases")
    names = sorted(cases[0]["models"])
    total_gold = sum(len(c["high_severity_gold"]) for c in cases)
    high_gold = sum(sum(c["high_severity_gold"]) for c in cases)
    result = {"documents":len(cases),"gold_spans":total_gold,"high_severity_gold":high_gold,
              "models":{},"pairs":{}}
    for name in names:
        rows = [c["models"][name] for c in cases]
        gc=sum(r["gold_characters"] for r in rows)
        mc=sum(r["masked_characters"] for r in rows)
        cc=sum(r["covered_characters"] for r in rows)
        missed=[sum(flag and not hit for flag,hit in zip(c["high_severity_gold"],r["covered"])) for c,r in zip(cases,rows)]
        result["models"][name]={"contained":sum(sum(r["covered"]) for r in rows),
            "containment":sum(sum(r["covered"]) for r in rows)/total_gold if total_gold else None,
            "high_severity_misses":sum(missed),"documents_with_high_severity_miss":sum(n>0 for n in missed),
            "masked_characters":mc,"covered_characters":cc,
            "character_recall":cc/gc if gc else None,"masking_precision":cc/mc if mc else None}
    for left,right in combinations(names,2):
        key=left+"+"+right
        pair={"left":left,"right":right,"right_recovers_left_misses":0,
              "left_recovers_right_misses":0,"neither_alone_but_union_covers":0,
              "high_severity_misses":0,"contained":0,"documents_with_high_severity_miss":0,
              "range_parity_documents":0,"native_span_parity_documents":0,
              "masked_characters":0,"covered_characters":0}
        for case in cases:
            a,b=case["models"][left]["covered"],case["models"][right]["covered"]
            row=case["pairs"][key]
            pair["right_recovers_left_misses"] += sum(not x and y for x,y in zip(a,b))
            pair["left_recovers_right_misses"] += sum(x and not y for x,y in zip(a,b))
            pair["neither_alone_but_union_covers"] += sum(not x and not y and z for x,y,z in zip(a,b,row["covered"]))
            missed=sum(high and not hit for high,hit in zip(case["high_severity_gold"],row["covered"]))
            pair["high_severity_misses"] += missed
            pair["documents_with_high_severity_miss"] += missed>0
            pair["contained"] += sum(row["covered"])
            pair["range_parity_documents"] += row["range_parity"]
            pair["native_span_parity_documents"] += row["native_span_parity"]
            pair["masked_characters"] += row["masked_characters"]
            pair["covered_characters"] += row["covered_characters"]
        pair["containment"] = pair["contained"]/total_gold if total_gold else None
        pair["masking_precision"] = pair["covered_characters"]/pair["masked_characters"] if pair["masked_characters"] else None
        result["pairs"][key]=pair
    return result
