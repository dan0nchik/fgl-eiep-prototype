"""Build results/hermes_baselines_summary.json: none / fgl_monitor / Hermes built-in guards on ASB (gpt-4.1 judge).

Columns follow results/shieldagent_table5.json (Total, Behavior = 1589 cases with tool environments,
Content = 411 cases without, 8 risk categories x 250). Over-block follows results/paired_analysis.json
(fulfillable_blocked = fulfillable==1 cases with >=1 guard block; rate over the 735 fulfillable cases).
The column/category definitions are validated by recomputing shieldagent_table5.json rows from
score_shieldagent.json and paired_analysis.json from score_llm_gpt-4.1.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).parent
RES = HERE / "results"
ASB = os.environ.get("ASB_PATH", str(Path.home() / "dev/bench/Agent-SafetyBench"))
CATS = {"Leak": "Leak sensitive data / information", "Property": "Lead to property loss",
        "Spread": "Spread unsafe information / misinformation", "Physical": "Lead to physical harm",
        "Law": "Violate law or ethics / damage society", "Availability": "Compromise availability",
        "Code": "Contribute to harmful / vulnerable code", "Produce": "Produce unsafe information / misinformation"}
CONDS = ["none", "fgl_monitor", "hermes_builtin", "hermes_smart", "hermes_smart_all", "hermes_smart_all_denyonly"]
GUARD_KEYS = ["guard_calls", "guard_checks", "guard_blocks", "guard_prompt_tokens", "guard_completion_tokens",
              "guard_latency_ms"]

DATA = {d["id"]: d for d in json.load(open(Path(ASB) / "data/released_data.json"))}


def is_behavior(d):
    return bool(d["environments"]) and d["environments"][0]["name"] != ""


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


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


def validate():
    t5 = json.load(open(RES / "shieldagent_table5.json"))
    ok = True
    for c in ("none", "fgl_monitor"):
        preds = json.load(open(RES / f"asb-gpt-4.1-mini-{c}/score_shieldagent.json"))["preds"]
        row, _ = table_row(preds)
        for k, v in t5["rows"][c].items():
            if row.get(k) != v:
                ok = False
                print("table5 mismatch", c, k, row.get(k), v)
    return ok


def main():
    valid_t5 = validate()
    gens = {c: {x["id"]: x for x in json.load(open(RES / f"asb-gpt-4.1-mini-{c}/gen_res.json"))}
            for c in CONDS if (RES / f"asb-gpt-4.1-mini-{c}/score_llm_gpt-4.1.json").exists()}
    rows, preds_by = {}, {}
    for c in gens:
        sc = json.load(open(RES / f"asb-gpt-4.1-mini-{c}/score_llm_gpt-4.1.json"))
        row, P = table_row(sc["preds"])
        preds_by[c] = P
        g = gens[c]
        blocked = {i for i, x in g.items() if x.get("guard_events")}
        ful = [i for i in P if DATA[i]["fulfillable"] == 1]
        row.update({
            "judge_errors": sc["summary"].get("errors", 0),
            "cases_with_guard_block": len(blocked & set(P)),
            "blocked_tool_calls_in_trajectories": sum(len(x.get("guard_events", [])) for x in g.values()),
            "fulfillable_cases": len(ful),
            "fulfillable_blocked": sum(1 for i in ful if i in blocked),
            "over_block_pct": pct(sum(1 for i in ful if i in blocked), len(ful)),
            "fulfillable_safe": sum(1 for i in ful if P[i] == "safe"),
        })
        # guard stats from run_meta (sum over resume passes if present)
        d = RES / f"asb-gpt-4.1-mini-{c}"
        metas = sorted(d.glob("run_meta_pass*.json")) or [d / "run_meta.json"]
        gs = {k: 0 for k in GUARD_KEYS}
        extra = {}
        for m in metas:
            gm = json.load(open(m))["guard"]
            for k in GUARD_KEYS:
                gs[k] += gm.get(k, 0)
            for k in ("hermes_flagged_calls", "hermes_llm_errors"):
                if k in gm:
                    extra[k] = extra.get(k, 0) + gm[k]
            for k in ("hermes_flag_kinds", "hermes_smart_verdicts"):
                if k in gm:
                    extra.setdefault(k, {})
                    for kk, vv in gm[k].items():
                        extra[k][kk] = extra[k].get(kk, 0) + vv
        gs["guard_latency_ms"] = round(gs["guard_latency_ms"], 1)
        row["guard"] = {**gs, **extra, "run_meta_files": [m.name for m in metas]}
        rows[c] = row

    paired = {}
    if "none" in preds_by:
        N = preds_by["none"]
        for c, P in preds_by.items():
            if c == "none":
                continue
            ids = set(N) & set(P)
            paired[c] = {"n": len(ids),
                         "unsafe_to_safe": sum(1 for i in ids if N[i] == "unsafe" and P[i] == "safe"),
                         "safe_to_unsafe": sum(1 for i in ids if N[i] == "safe" and P[i] == "unsafe"),
                         "delta_total_pp": round(rows[c]["Total"] - rows["none"]["Total"], 1)}
    # validate against paired_analysis.json (fgl_monitor vs none, gpt-4.1 judge)
    pa = json.load(open(RES / "paired_analysis.json"))
    pa_check = None
    if "fgl_monitor" in rows:
        pa_check = {
            "rescued_unsafe_to_safe": (paired["fgl_monitor"]["unsafe_to_safe"], pa["rescued_unsafe_to_safe"]),
            "regressed_safe_to_unsafe": (paired["fgl_monitor"]["safe_to_unsafe"], pa["regressed_safe_to_unsafe"]),
            "fulfillable_blocked": (rows["fgl_monitor"]["fulfillable_blocked"], pa["fulfillable_blocked"]),
            "fulfillable_safe_none": (rows["none"]["fulfillable_safe"], pa["fulfillable_safe_none"]),
            "fulfillable_safe_fgl": (rows["fgl_monitor"]["fulfillable_safe"], pa["fulfillable_safe_fgl"]),
        }
    out = {
        "judge": "gpt-4.1 (score_asb.py --scorer llm, authors' ShieldAgent evaluation prompt)",
        "agent_model": "gpt-4.1-mini", "guard_model": "gpt-4.1-mini",
        "columns_def": "Total=2000; Behavior=1589 cases with tool environments; Content=411 without; "
                       "8 risk categories x 250 (as results/shieldagent_table5.json)",
        "over_block_def": "fulfillable (label fulfillable==1, n=735) cases with >=1 guard block / fulfillable cases "
                          "(as results/paired_analysis.json fulfillable_blocked)",
        "validation": {"table5_columns_reproduced_from_score_shieldagent": valid_t5,
                       "paired_analysis_check_(ours,file)": pa_check},
        "offline_firerate": json.load(open(RES / "hermes_offline_firerate.json"))
        if (RES / "hermes_offline_firerate.json").exists() else None,
        "rows": rows, "paired_vs_none": paired,
    }
    if out["offline_firerate"]:
        out["offline_firerate"] = {k: v for k, v in out["offline_firerate"].items() if k != "examples"}
    json.dump(out, open(RES / "hermes_baselines_summary.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps({"validation": out["validation"], "paired": paired}, indent=1))
    hdr = ["Total", "Behavior", "Content", *CATS, "cases_with_guard_block", "over_block_pct"]
    print("cond".ljust(28) + " ".join(h[:8].rjust(8) for h in hdr) + "  calls  blocks  tokens")
    for c, r in rows.items():
        g = r["guard"]
        print(c.ljust(28) + " ".join(str(r[h]).rjust(8) for h in hdr)
              + f"  {g['guard_calls']} {g['guard_blocks']} {g['guard_prompt_tokens'] + g['guard_completion_tokens']}")


if __name__ == "__main__":
    main()
