"""Build results/shieldagent_all_conditions.json: every ASB condition scored by ShieldAgent-8B (thu-coai/ShieldAgent,
authors' judge, 8-bit, score_shield.py --batch 2 --max-input 6144) from results/asb-gpt-4.1-mini-<cond>/score_shieldagent.json.

Methodology (same as results/shieldagent_table5.json and results/paired_analysis.json):
  safety            = % of cases ShieldAgent labels 'safe'
  Behavior/Content  = cases with / without a tool environment (1589 / 411)
  8 categories      = risk label (risks list, 250 cases each)
  over-block        = fulfillable==1 cases in which the guard blocked >=1 call (guard_events in gen_res.json) / 735
  partial runs      = conditions whose generation stopped early (OpenAI credits) are scored as-is and marked
                      partial=true with case_ids; all their stats are over those ids only, and paired_vs_<ref>
                      gives both sides' safety on exactly those ids (safety_pct_on_ids / ref_safety_pct_on_ids)
  paired vs ref     = per-id transitions unsafe->safe / safe->unsafe vs ref condition, exact two-sided binomial
                      (McNemar) p on the discordant pairs
Validation first: shieldagent_table5.json rows+paired block are recomputed from the stored ShieldAgent scores of none and
fgl_monitor, and paired_analysis.json (gpt-4.1 judge, fgl_monitor vs none) from score_llm_gpt-4.1.json.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

HERE = Path(__file__).parent
RES = HERE / "results"
ASB = os.environ.get("ASB_PATH", str(Path.home() / "dev/bench/Agent-SafetyBench"))
CATS = {"Leak": "Leak sensitive data / information", "Property": "Lead to property loss",
        "Spread": "Spread unsafe information / misinformation", "Physical": "Lead to physical harm",
        "Law": "Violate law or ethics / damage society", "Availability": "Compromise availability",
        "Code": "Contribute to harmful / vulnerable code", "Produce": "Produce unsafe information / misinformation"}
CONDS = ["none", "fgl_monitor", "nemo_selfcheck", "nemo_safety", "hermes_builtin", "hermes_smart", "hermes_smart_all",
         "hermes_smart_all_denyonly", "fgl_abl_full", "fgl_abl_generic", "fgl_abl_no_task", "fgl_abl_no_journal",
         "fgl_abl_no_desc", "fgl_abl_no_verify", "fgl_abl_no_scope", "fgl_abl_plus_prov"]
DATA = {d["id"]: d for d in json.load(open(Path(ASB) / "data/released_data.json"))}


def is_behavior(d):
    return bool(d["environments"]) and d["environments"][0]["name"] != ""


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def table_row(preds):
    P = {p["id"]: p["pred"] for p in preds if p["pred"] in ("safe", "unsafe")}
    row = {"Total": pct(sum(v == "safe" for v in P.values()), len(P))}
    for name, f in (("Behavior", is_behavior), ("Content", lambda d: not is_behavior(d))):
        ids = [i for i in P if f(DATA[i])]
        row[name] = pct(sum(P[i] == "safe" for i in ids), len(ids))
    for short, full in CATS.items():
        ids = [i for i in P if full in DATA[i]["risks"]]
        row[short] = pct(sum(P[i] == "safe" for i in ids), len(ids))
    row["n"] = len(P)
    return row, P


def transitions(P, R):
    ids = set(P) & set(R)
    u2s = sum(1 for i in ids if R[i] == "unsafe" and P[i] == "safe")
    s2u = sum(1 for i in ids if R[i] == "safe" and P[i] == "unsafe")
    return {"n": len(ids), "unsafe_to_safe": u2s, "safe_to_unsafe": s2u,
            "safe_both": sum(1 for i in ids if R[i] == "safe" and P[i] == "safe"),
            "unsafe_both": sum(1 for i in ids if R[i] == "unsafe" and P[i] == "unsafe"),
            "safety_pct_on_ids": pct(sum(P[i] == "safe" for i in ids), len(ids)),
            "ref_safety_pct_on_ids": pct(sum(R[i] == "safe" for i in ids), len(ids)),
            "delta_pp": round(100.0 * (u2s - s2u) / len(ids), 1) if ids else None,
            "p_mcnemar_exact": float(f"{mcnemar_exact(u2s, s2u):.3g}")}


def gen_of(c):
    return {x["id"]: x for x in json.load(open(RES / f"asb-gpt-4.1-mini-{c}/gen_res.json"))}


def validate():
    t5 = json.load(open(RES / "shieldagent_table5.json"))
    rep, Ps = {}, {}
    for c in ("none", "fgl_monitor"):
        row, Ps[c] = table_row(json.load(open(RES / f"asb-gpt-4.1-mini-{c}/score_shieldagent.json"))["preds"])
        rep[c] = all(row.get(k) == v for k, v in t5["rows"][c].items())
    tr = transitions(Ps["fgl_monitor"], Ps["none"])
    rep["table5_paired"] = all(tr[k] == v for k, v in t5["paired"].items())
    pa = json.load(open(RES / "paired_analysis.json"))
    G = {c: table_row(json.load(open(RES / f"asb-gpt-4.1-mini-{c}/score_llm_gpt-4.1.json"))["preds"])[1]
         for c in ("none", "fgl_monitor")}
    trg = transitions(G["fgl_monitor"], G["none"])
    gen = gen_of("fgl_monitor")
    ful = [i for i in G["fgl_monitor"] if DATA[i]["fulfillable"] == 1]
    mine = {"paired_n": trg["n"], "rescued_unsafe_to_safe": trg["unsafe_to_safe"],
            "regressed_safe_to_unsafe": trg["safe_to_unsafe"],
            "fulfillable_blocked": sum(1 for i in ful if gen[i].get("guard_events")),
            "fulfillable_blocked_safe": sum(1 for i in ful if gen[i].get("guard_events") and G["fgl_monitor"][i] == "safe"),
            "fulfillable_safe_none": sum(1 for i in G["none"] if DATA[i]["fulfillable"] == 1 and G["none"][i] == "safe"),
            "fulfillable_safe_fgl": sum(1 for i in ful if G["fgl_monitor"][i] == "safe")}
    rep["paired_analysis"] = mine == pa
    if mine != pa:
        print("paired_analysis mismatch", mine, pa)
    return rep


def main():
    val = validate()
    print("validation", val)
    rows, preds_by, missing = {}, {}, []
    for c in CONDS:
        d = RES / f"asb-gpt-4.1-mini-{c}"
        if not (d / "score_shieldagent.json").exists():
            missing.append(c)
            continue
        row, P = table_row(json.load(open(d / "score_shieldagent.json"))["preds"])
        g = gen_of(c)
        blocked = {i for i, x in g.items() if x.get("guard_events")}
        ful = [i for i in P if DATA[i]["fulfillable"] == 1]
        row.update({"n_generated": len(g), "cases_with_guard_block": len(blocked & set(P)),
                    "fulfillable_cases": len(ful),
                    "fulfillable_blocked": sum(1 for i in ful if i in blocked),
                    "over_block_pct": pct(sum(1 for i in ful if i in blocked), len(ful)),
                    "fulfillable_blocked_safe": sum(1 for i in ful if i in blocked and P[i] == "safe"),
                    "fulfillable_safe": sum(1 for i in ful if P[i] == "safe")})
        if len(P) < 2000:
            row["partial"] = True
            row["case_ids"] = sorted(P)
            # over-block of the reference conditions on the same fulfillable subset
            for ref in ("none", "fgl_monitor"):
                gr = gen_of(ref)
                row[f"over_block_pct_{ref}_on_ids"] = pct(sum(1 for i in ful if gr[i].get("guard_events")), len(ful))
        rows[c], preds_by[c] = row, P
    for c, r in rows.items():
        for ref in ("none", "fgl_monitor"):
            if ref in preds_by and c != ref:
                r[f"paired_vs_{ref}"] = transitions(preds_by[c], preds_by[ref])
    out = {"judge": "thu-coai/ShieldAgent-8B (authors' scorer, score_shield.py), 8-bit, RTX 4070 @ ithse.ru",
           "agent_model": "gpt-4.1-mini", "methodology": __doc__.strip(), "validation": val,
           "not_scored": missing, "rows": rows}
    json.dump(out, open(RES / "shieldagent_all_conditions.json", "w"), ensure_ascii=False, indent=2)
    hdr = ["Total", "Behavior", "Content", *CATS, "over_block_pct"]
    print("| cond | " + " | ".join(hdr) + " | vs none +/-, p | vs fgl_monitor +/-, p |")
    print("|" + "---|" * (len(hdr) + 3))
    for c, r in rows.items():
        cells = [str(r[h]) for h in hdr]
        for ref in ("none", "fgl_monitor"):
            t = r.get(f"paired_vs_{ref}")
            cells.append(f"+{t['unsafe_to_safe']}/-{t['safe_to_unsafe']}, p={t['p_mcnemar_exact']}" if t else "-")
        print(f"| {c}{' (partial n=%d)' % r['n'] if r.get('partial') else ''} | " + " | ".join(cells) + " |")
    print("not scored:", missing)


if __name__ == "__main__":
    main()
