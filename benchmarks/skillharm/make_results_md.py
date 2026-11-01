#!/usr/bin/env python3
"""(local) Render the per-condition tables section of RESULTS.md from results/*_summary.json + comparisons.json.
Prose sections (setup, deviations, caveats) are written by hand around the generated block.
usage: make_results_md.py RESULTS_DIR > tables.md"""
import json, os, sys, glob
d = sys.argv[1]
S = {os.path.basename(f)[:-len("_summary.json")]: json.load(open(f)) for f in glob.glob(f"{d}/*_summary.json")}
C = json.load(open(f"{d}/comparisons.json")) if os.path.isfile(f"{d}/comparisons.json") else {}
order = ["none", "authors", "fgl", "fgl_no_taskfit", "fgl_no_provenance", "fgl_no_scope", "fgl_no_irrev", "fgl_no_explicit_list"]
conds = [c for c in order if c in S] + sorted(c for c in S if c not in order)
def f(r):
    if not r or not r.get("n"): return "n/a"
    return f"{100*r['rate']:.1f}% ({r['success']}/{r['n']})"
print("### ASR and benign utility per condition\n")
print("| condition | FPP ASR | SMP ASR | overall ASR | benign task success | FPP task success under attack |")
print("|---|---|---|---|---|---|")
for c in conds:
    s = S[c]
    print(f"| {c} | {f(s['asr_by_scenario']['FPP'])} | {f(s['asr_by_scenario']['SMP'])} | {f(s['asr_overall'])} | {f(s['benign_success'])} | {f(s['attack_task_utility']['FPP'])} |")
print("\n### ASR by workflow component (FPP+SMP pooled)\n")
comps = sorted(next(iter(S.values()))["asr_by_component"])
print("| condition | " + " | ".join(comps) + " |"); print("|---" * (len(comps) + 1) + "|")
for c in conds: print(f"| {c} | " + " | ".join(f(S[c]['asr_by_component'][k]) for k in comps) + " |")
print("\n### ASR by risk type (FPP+SMP pooled)\n")
risks = sorted(next(iter(S.values()))["asr_by_risk"])
print("| risk | " + " | ".join(conds) + " |"); print("|---" * (len(conds) + 1) + "|")
for r in risks: print(f"| {r} | " + " | ".join(f(S[c]['asr_by_risk'][r]) for c in conds) + " |")
print("\n### Paired comparisons against `fgl` (same samples, exact McNemar)\n")
print("| comparison | paired n | other | fgl | only other positive | only fgl positive | p |")
print("|---|---|---|---|---|---|---|")
for k, v in C.items():
    print(f"| {k} ({v['metric']}) | {v['paired_n']} | {100*v['other_rate']:.1f}% | {100*v['fgl_rate']:.1f}% | {v['only_other_positive']} | {v['only_fgl_positive']} | {v['mcnemar_exact_p']} |")
J = {c: S[c].get("judge") for c in conds if S[c].get("judge")}
if J:
    print("\n### LLM-judge metrics (authors' judge prompt; judge = gpt-5.6-terra via codex exec)\n")
    print("| condition | judged n | engaged (used target file) | cASR | ARR (refusal) | identified |"); print("|---|---|---|---|---|---|")
    for c, j in J.items(): print(f"| {c} | {j['n_judged']} | {j['engaged_n']} | {f(j['cASR'])} | {f(j['refusal_rate_ARR'])} | {f(j['identified_rate'])} |")
print("\n### Codex token usage per condition (all trials incl. benign)\n")
print("| condition | input tokens | cached input | output tokens |"); print("|---|---|---|---|")
for c in conds:
    t = S[c]["tokens"]; print(f"| {c} | {t.get('input_tokens',0):,} | {t.get('cached_input_tokens',0):,} | {t.get('output_tokens',0):,} |")
