"""Aggregate the FGL-monitor ablation runs on Agent-SafetyBench into results/fgl_ablation_summary.json.

Methodology (same as results/shieldagent_table5.json and results/paired_analysis.json):
  safety            = % of cases the judge labels 'safe' (judge errors excluded)
  Behavior/Content  = cases with / without a tool environment (1589 / 411)
  8 categories      = the case's risk label (risks[0], 250 cases each)
  over-block        = fulfillable==1 cases in which the guard blocked at least one call (/ 735 fulfillable)
  paired vs ref     = per-id transitions unsafe->safe / safe->unsafe, exact two-sided binomial (McNemar) p
Judges: ShieldAgent-8B (score_shieldagent.json, primary) and gpt-4.1 with the authors' prompt
(score_llm_gpt-4.1.json, secondary).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

HERE = Path(__file__).parent
RES = HERE / "results"
ASB = os.environ.get("ASB_PATH", str(Path.home() / "dev/bench/Agent-SafetyBench"))
AGENT = "gpt-4.1-mini"
CONDS = ["none", "fgl_monitor", "fgl_abl_full", "fgl_abl_no_task", "fgl_abl_no_journal", "fgl_abl_no_desc",
         "fgl_abl_no_verify", "fgl_abl_no_scope", "fgl_abl_generic", "fgl_abl_plus_prov"]
CATS = {"Leak": "Leak sensitive data / information", "Property": "Lead to property loss",
        "Spread": "Spread unsafe information / misinformation", "Physical": "Lead to physical harm",
        "Law": "Violate law or ethics / damage society", "Availability": "Compromise availability",
        "Code": "Contribute to harmful / vulnerable code", "Produce": "Produce unsafe information / misinformation"}
JUDGES = {"shieldagent": "score_shieldagent.json", "gpt-4.1": "score_llm_gpt-4.1.json"}
# fgl_abl_full and fgl_abl_no_verify are PARTIAL: the OpenAI key ran out of credits mid-run (2026-11-01) and no further
# gpt-4.1-mini generation was possible. A guard call that errors fails OPEN (allows the action), so each run is kept
# only up to its last progress checkpoint with guard_errors == 0: fgl_abl_no_verify 729 cases (as saved),
# fgl_abl_full 576 cases (truncated from 689; 2 fail-opens by checkpoint 586). run_meta.json was never written for
# them, so their guard stats are taken from that checkpoint's progress line (/tmp/abl/<cond>.gen.log); these
# include calls in flight for cases that were not saved (slight overcount).
PARTIAL = {
    "fgl_abl_full": {"guard_calls": 885, "guard_checks": 889, "guard_blocks": 260, "guard_prompt_tokens": 384706,
                     "guard_completion_tokens": 24073, "guard_errors": 0, "cases": 576},
    "fgl_abl_no_verify": {"guard_calls": 943, "guard_checks": 949, "guard_blocks": 270, "guard_prompt_tokens": 373047,
                          "guard_completion_tokens": 25428, "guard_errors": 0, "cases": 729},
}


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def pct(xs):
    xs = list(xs)
    return round(100.0 * sum(xs) / len(xs), 1) if xs else None


def load(cond, judge_file):
    d = RES / f"asb-{AGENT}-{cond}"
    if not (d / judge_file).exists() or not (d / "gen_res.json").exists():
        return None
    preds = {p["id"]: p for p in json.load(open(d / judge_file))["preds"]}
    gen = {x["id"]: x for x in json.load(open(d / "gen_res.json"))}
    meta = json.load(open(d / "run_meta.json")) if (d / "run_meta.json").exists() else {}
    if cond in PARTIAL and not meta:
        meta = {"guard": {k: v for k, v in PARTIAL[cond].items() if k != "cases"}, "partial_run": PARTIAL[cond]}
    return preds, gen, meta


def table(judge_file, data, has_env):
    loaded = {c: load(c, judge_file) for c in CONDS}
    safe = {c: {i: p["pred"] == "safe" for i, p in v[0].items() if p["pred"] in ("safe", "unsafe") and i in v[1]}
            for c, v in loaded.items() if v}
    rows = {}
    for c, v in loaded.items():
        if not v:
            continue
        preds, gen, meta = v
        s = safe[c]
        blocked = {i: len(gen[i].get("guard_events", [])) > 0 for i in gen}
        ful = [i for i in s if data[i]["fulfillable"] == 1]
        g = meta.get("guard", {})
        tok = (g.get("guard_prompt_tokens", 0) + g.get("guard_completion_tokens", 0)) if g else None
        row = {
            "n_scored": len(s), "judge_errors": sum(1 for p in preds.values() if p["pred"] not in ("safe", "unsafe")),
            "n_generated": len(gen), "complete": len(gen) == 2000 and len(s) == 2000,
            "Total": pct(s.values()),
            "Behavior": pct(s[i] for i in s if has_env[i]),
            "Content": pct(s[i] for i in s if not has_env[i]),
            **{k: pct(s[i] for i in s if data[i]["risks"][0] == lab) for k, lab in CATS.items()},
            "guard_blocks_calls": g.get("guard_blocks"),
            "guard_checks": g.get("guard_checks"),
            "guard_errors_failopen": g.get("guard_errors", 0 if g.get("guard_checks") == g.get("guard_calls") else None),
            "cases_with_block": sum(1 for i in s if blocked.get(i)),
            "guard_prompt_tokens": g.get("guard_prompt_tokens"),
            "guard_completion_tokens": g.get("guard_completion_tokens"),
            "guard_tokens_total": tok,
            "guard_tokens_per_call": round(tok / g["guard_calls"]) if g.get("guard_calls") else None,
            "fulfillable_n": len(ful),
            "fulfillable_blocked": sum(1 for i in ful if blocked.get(i)),
            "fulfillable_blocked_pct": pct(blocked.get(i, False) for i in ful),
            "fulfillable_blocked_safe": sum(1 for i in ful if blocked.get(i) and s[i]),
            "fulfillable_safe": sum(1 for i in ful if s[i]),
        }
        if "prov_tag_counts" in g:
            row["prov_tag_counts"] = g["prov_tag_counts"]
        if "partial_run" in meta:
            row["partial_run_guard_stats_from_checkpoint"] = True
        if not row["complete"]:   # partial run: reference safety on exactly the same case ids
            row["ref_total_on_same_ids"] = {ref: pct(safe[ref][i] for i in s if i in safe[ref])
                                            for ref in ("none", "fgl_monitor") if ref in safe}
            row["Total_on_ids_scored_by_refs"] = pct(s[i] for i in s if all(i in safe[r] for r in ("none", "fgl_monitor") if r in safe))
        for ref in ("fgl_monitor", "fgl_abl_full", "none"):
            if ref in safe and c != ref:
                common = sorted(set(s) & set(safe[ref]))
                u2s = sum(1 for i in common if s[i] and not safe[ref][i])
                s2u = sum(1 for i in common if not s[i] and safe[ref][i])
                row[f"paired_vs_{ref}"] = {
                    "n": len(common), "unsafe_to_safe": u2s, "safe_to_unsafe": s2u,
                    "delta_pp": round(100.0 * (u2s - s2u) / len(common), 1) if common else None,
                    "p_exact_binomial": float(f"{mcnemar_exact(u2s, s2u):.3g}")}
        rows[c] = row
    return rows


def show(rows):
    cols = ["n_scored", "Total", "Behavior", "Content", *CATS, "cases_with_block", "guard_blocks_calls",
            "fulfillable_blocked_pct", "guard_tokens_total"]
    print("cond".ljust(20) + " ".join(k[:8].rjust(8) for k in cols) + "  vs fgl_monitor (u2s/s2u, d, p)")
    for c, r in rows.items():
        pv = r.get("paired_vs_fgl_monitor")
        print(c.ljust(20) + " ".join(str(r[k]).rjust(8) for k in cols)
              + (f"  +{pv['unsafe_to_safe']}/-{pv['safe_to_unsafe']} d={pv['delta_pp']} p={pv['p_exact_binomial']}"
                 if pv else ""))


def main():
    data = {x["id"]: x for x in json.load(open(Path(ASB) / "data/released_data.json"))}
    has_env = {i: bool(x["environments"] and x["environments"][0]["name"]) for i, x in data.items()}
    out = {"benchmark": "Agent-SafetyBench (2000 cases)", "agent_model": AGENT, "guard_model": "gpt-4.1-mini",
           "judges": {"shieldagent": "thu-coai/ShieldAgent-8B (authors' scorer), PRIMARY",
                      "gpt-4.1": "gpt-4.1 with the authors' ShieldAgent prompt (score_asb.py --scorer llm), secondary"},
           "methodology": __doc__.strip(),
           "note": "judge errors (e.g. 429) are excluded per condition; paired stats use ids scored in both conditions; "
                   "'complete' is false when gen_res or the judge file covers < 2000 cases",
           "rows": {j: table(f, data, has_env) for j, f in JUDGES.items()}}
    json.dump(out, open(RES / "fgl_ablation_summary.json", "w"), ensure_ascii=False, indent=2)
    for j, rows in out["rows"].items():
        print(f"\n== judge: {j}")
        show(rows)


def print_md(S):
    """Markdown tables used in FGL_ABLATION.md (python analyze_ablation.py --md)."""
    ORDER=["none","fgl_monitor","fgl_abl_full","fgl_abl_no_task","fgl_abl_no_journal","fgl_abl_no_desc","fgl_abl_no_verify","fgl_abl_no_scope","fgl_abl_generic","fgl_abl_plus_prov"]
    MCATS=["Leak","Property","Spread","Physical","Law","Availability","Code","Produce"]
    def f(x): return "n/a" if x is None else str(x)
    for j,rows0 in S["rows"].items():
        rows = {c:r for c,r in rows0.items() if j=="shieldagent" or r["complete"]}
        print(f"\n### Judge: {j}" + (" (primary)" if j=="shieldagent" else " (secondary; only conditions whose generation AND gpt-4.1 judging are complete)") + "\n")
        print("| Condition | n scored | Total | Behavior | Content | vs fgl_monitor: unsafe→safe / safe→unsafe | Δ pp | p (exact) | vs fgl_abl_full (replicate): Δ pp, p | fgl_monitor / none on the same ids |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for c in ORDER:
            if c not in rows:
                why = "not run (no API credits)" if c=="fgl_abl_plus_prov" else ("not scored by this judge" if c not in rows0 else "gpt-4.1 judging incomplete (429), see json")
                print(f"| {c} | {why} | | | | | | | | |"); continue
            r=rows[c]; pv=r.get("paired_vs_fgl_monitor"); pf=r.get("paired_vs_fgl_abl_full")
            print(f"| {c} | {r['n_scored']}{'' if r['complete'] else ' (PARTIAL)'} | {r['Total']} | {r['Behavior']} | {r['Content']} | "
                  + (f"{pv['unsafe_to_safe']} / {pv['safe_to_unsafe']} | {pv['delta_pp']:+} | {pv['p_exact_binomial']} |" if pv else "ref | | |")
                  + (f" {pf['delta_pp']:+}, p={pf['p_exact_binomial']} (n={pf['n']}) |" if pf else " |")
                  + (f" {r['ref_total_on_same_ids'].get('fgl_monitor')} / {r['ref_total_on_same_ids'].get('none')} |" if r.get('ref_total_on_same_ids') else " = full set |"))
        print("\n| Condition | " + " | ".join(MCATS) + " |\n|---|" + "---|"*len(MCATS))
        for c in ORDER:
            if c in rows: print(f"| {c} | " + " | ".join(f(rows[c][k]) for k in MCATS) + " |")
        print("\n| Condition | cases with ≥1 block | blocked calls | guard calls | guard tokens (total) | tokens / call | fulfillable blocked (of 735) | fulfillable blocked % | fulfillable judged safe |")
        print("|---|---|---|---|---|---|---|---|---|")
        for c in ORDER:
            if c in rows:
                r=rows[c]; print(f"| {c} | {r['cases_with_block']} | {f(r['guard_blocks_calls'])} | {f(r['guard_checks'])} | {f(r['guard_tokens_total'])} | {f(r['guard_tokens_per_call'])} | {r['fulfillable_blocked']} of {r['fulfillable_n']} | {r['fulfillable_blocked_pct']} | {r['fulfillable_safe']} |")


if __name__ == "__main__":
    import sys
    if "--md" in sys.argv:
        print_md(json.load(open(RES / "fgl_ablation_summary.json")))
    else:
        main()
