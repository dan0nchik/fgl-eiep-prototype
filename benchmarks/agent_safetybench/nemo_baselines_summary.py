"""Build results/nemo_baselines_summary.json: NeMo Guardrails baselines vs none / fgl_monitor on ASB (gpt-4.1 judge).

Column definitions are the same as results/shieldagent_table5.json (Total; Behavior = cases with a tool
environment, n=1589; Content = cases without, n=411; 8 risk categories x 250 by risks[0]). Over-block follows
results/paired_analysis.json (fulfillable==1 cases with >=1 guard block, over the 735 fulfillable cases).
Both definitions are validated here by recomputing table5 (ShieldAgent preds) and paired_analysis (gpt-4.1 preds).
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
CONDS = ["none", "fgl_monitor", "nemo_selfcheck", "nemo_safety"]
GUARD_SUM = ["guard_calls", "guard_checks", "guard_blocks", "guard_prompt_tokens", "guard_completion_tokens",
             "guard_latency_ms", "nemo_input_checks", "nemo_input_blocks", "nemo_output_blocks",
             "nemo_blocks_by_input", "nemo_errors"]
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


def validate_table5():
    t5 = json.load(open(RES / "shieldagent_table5.json"))
    for c in ("none", "fgl_monitor"):
        row, _ = table_row(json.load(open(RES / f"asb-gpt-4.1-mini-{c}/score_shieldagent.json"))["preds"])
        for k, v in t5["rows"][c].items():
            if row.get(k) != v:
                return False
    return True


def stage(ev):
    r = ev.get("reason", "")
    return "input" if "input rail" in r else ("output" if "output rail" in r else "other")


def main():
    rows, preds_by = {}, {}
    for c in CONDS:
        d = RES / f"asb-gpt-4.1-mini-{c}"
        if not (d / "score_llm_gpt-4.1.json").exists():
            continue
        sc = json.load(open(d / "score_llm_gpt-4.1.json"))
        g = {x["id"]: x for x in json.load(open(d / "gen_res.json"))}
        row, P = table_row(sc["preds"])
        preds_by[c] = P
        blocked = {i for i, x in g.items() if x.get("guard_events")}
        ful = [i for i in P if DATA[i]["fulfillable"] == 1]
        ful_blk = [i for i in ful if i in blocked]
        row.update({
            "judge_errors": sc["summary"].get("errors", 0),
            "cases_with_guard_block": len(blocked & set(P)),
            "blocked_tool_calls_in_trajectories": sum(len(x.get("guard_events", [])) for x in g.values()),
            "fulfillable_cases": len(ful), "fulfillable_blocked": len(ful_blk),
            "over_block_pct": pct(len(ful_blk), len(ful)),
            "fulfillable_safe": sum(1 for i in ful if P[i] == "safe"),
            "safe_among_blocked_pct": pct(sum(1 for i in blocked if P.get(i) == "safe"), len(blocked & set(P))),
        })
        # judge-free guard metrics over ALL 2000 trajectories (do not depend on judge coverage)
        ful_all = [i for i in g if DATA[i]["fulfillable"] == 1]
        row["guard_all_cases"] = {
            "n_trajectories": len(g), "cases_with_guard_block": len(blocked),
            "fulfillable_cases": len(ful_all),
            "fulfillable_blocked": sum(1 for i in ful_all if i in blocked),
            "over_block_pct": pct(sum(1 for i in ful_all if i in blocked), len(ful_all)),
            "unfulfillable_blocked": sum(1 for i in g if DATA[i]["fulfillable"] == 0 and i in blocked),
            "behavior_cases_with_block": sum(1 for i in blocked if is_behavior(DATA[i])),
            "cases_with_tool_call": sum(1 for x in g.values() if any(m.get("tool_calls") for m in x["output"]
                                                                     if m.get("role") == "assistant"))}
        if c.startswith("nemo"):
            st = {"input": 0, "output": 0, "other": 0}
            st_ful = {"input": 0, "output": 0, "other": 0}
            for i, x in g.items():
                kinds = {stage(e) for e in x.get("guard_events", [])}
                for k in kinds:
                    st[k] += 1
                    if DATA[i]["fulfillable"] == 1:
                        st_ful[k] += 1
            row["cases_blocked_by_stage"] = st
            row["fulfillable_cases_blocked_by_stage"] = st_ful
        metas = sorted(d.glob("run_meta_pass*.json")) or [d / "run_meta.json"]
        gs = {}
        for m in metas:
            gm = json.load(open(m))["guard"]
            for k in GUARD_SUM:
                if k in gm:
                    gs[k] = gs.get(k, 0) + gm[k]
        if "guard_latency_ms" in gs:
            gs["guard_latency_ms"] = round(gs["guard_latency_ms"], 1)
            gs["mean_latency_ms_per_checked_call"] = round(gs["guard_latency_ms"] / gs["guard_checks"], 1) \
                if gs.get("guard_checks") else None
        gs["run_meta_files"] = [m.name for m in metas]
        row["guard"] = gs
        rows[c] = row

    paired = {}
    N = preds_by.get("none", {})
    for c, P in preds_by.items():
        if c == "none" or not N:
            continue
        ids = set(N) & set(P)
        paired[c] = {"n": len(ids),
                     "unsafe_to_safe": sum(1 for i in ids if N[i] == "unsafe" and P[i] == "safe"),
                     "safe_to_unsafe": sum(1 for i in ids if N[i] == "safe" and P[i] == "unsafe"),
                     "delta_total_pp": round(rows[c]["Total"] - rows["none"]["Total"], 1)}
    # matched subset: ids judged (safe/unsafe) in EVERY condition. Needed when a judge run is incomplete
    # (e.g. API quota errors): compares all conditions on exactly the same cases.
    common = set.intersection(*(set(P) for P in preds_by.values())) if preds_by else set()
    matched = {}
    for c, P in preds_by.items():
        r, _ = table_row([{"id": i, "pred": P[i]} for i in common])
        g = {x["id"]: x for x in json.load(open(RES / f"asb-gpt-4.1-mini-{c}/gen_res.json"))}
        ful = [i for i in common if DATA[i]["fulfillable"] == 1]
        r["fulfillable_cases"] = len(ful)
        r["fulfillable_blocked"] = sum(1 for i in ful if g[i].get("guard_events"))
        r["over_block_pct"] = pct(r["fulfillable_blocked"], len(ful))
        r["cases_with_guard_block"] = sum(1 for i in common if g[i].get("guard_events"))
        matched[c] = r
    for c, r in rows.items():
        r["judge_coverage"] = f"{r['n']}/2000"
    pa = json.load(open(RES / "paired_analysis.json"))
    pa_ok = ("fgl_monitor" in paired and paired["fgl_monitor"]["unsafe_to_safe"] == pa["rescued_unsafe_to_safe"]
             and paired["fgl_monitor"]["safe_to_unsafe"] == pa["regressed_safe_to_unsafe"]
             and rows["fgl_monitor"]["fulfillable_blocked"] == pa["fulfillable_blocked"]
             and rows["none"]["fulfillable_safe"] == pa["fulfillable_safe_none"]
             and rows["fgl_monitor"]["fulfillable_safe"] == pa["fulfillable_safe_fgl"])
    try:
        import nemoguardrails
        ver = nemoguardrails.__version__
    except Exception:
        ver = "0.24.1 (import from the NeMo venv to confirm)"
    out = {
        "judge": "gpt-4.1 (score_asb.py --scorer llm, authors' ShieldAgent evaluation prompt)",
        "agent_model": "gpt-4.1-mini", "nemo_llm": "gpt-4.1-mini", "nemoguardrails_version": ver,
        "nemo_configs": {"nemo_selfcheck": "guards/nemo_configs/selfcheck", "nemo_safety": "guards/nemo_configs/safety"},
        "columns_def": "Total=2000; Behavior=1589 cases with tool environments; Content=411 without; "
                       "8 risk categories x 250 (as results/shieldagent_table5.json)",
        "over_block_def": "fulfillable (fulfillable==1, n=735) cases with >=1 guard block / fulfillable cases "
                          "(as results/paired_analysis.json fulfillable_blocked)",
        "validation": {"table5_columns_reproduced_from_score_shieldagent": validate_table5(),
                       "paired_analysis_reproduced": pa_ok},
        "rows": rows, "paired_vs_none": paired,
        "matched_subset": {"def": "cases judged safe/unsafe in every condition listed", "n": len(common),
                           "rows": matched},
    }
    json.dump(out, open(RES / "nemo_baselines_summary.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps({"validation": out["validation"], "paired": paired}, indent=1))
    hdr = ["Total", "Behavior", "Content", *CATS, "cases_with_guard_block", "over_block_pct"]
    print("cond".ljust(16) + " ".join(h[:8].rjust(8) for h in hdr) + "  calls blocks tokens errors")
    for c, r in rows.items():
        g = r["guard"]
        print(c.ljust(16) + " ".join(str(r[h]).rjust(8) for h in hdr)
              + f"  {g.get('guard_calls')} {g.get('guard_blocks')} "
                f"{g.get('guard_prompt_tokens', 0) + g.get('guard_completion_tokens', 0)} {g.get('nemo_errors', '-')}"
              + f"  judged {r['n']}")
    print(f"matched subset n={len(common)}")
    for c, r in matched.items():
        print(c.ljust(16) + " ".join(str(r[h]).rjust(8) for h in hdr) + f"  ful={r['fulfillable_cases']}")


if __name__ == "__main__":
    main()
