#!/usr/bin/env python3
"""Stratified SkillHarm subset: FPP k per risk type (spread over tasks), SMP k per risk type (or all).
Seed 0. Writes sample_ids.json + NL_SAMPLE_LIST TSV for the authors' eval.sh.
usage: make_sample.py DATA_DIR OUT_DIR [fpp_per_risk=8] [smp_per_risk=all]"""
import json, random, sys
from collections import defaultdict
data, out = sys.argv[1], sys.argv[2]
fpp_k = int(sys.argv[3]) if len(sys.argv) > 3 else 8
smp_k = sys.argv[4] if len(sys.argv) > 4 else "all"
rng = random.Random(0)

def load(p): return [json.loads(l) for l in open(p) if l.strip()]
fpp = load(f"{data}/fpp_index.jsonl"); smp = load(f"{data}/smp_index.jsonl")

def spread(rows, key, k):
    """Pick k rows maximizing diversity over `key`: shuffle, then round-robin over groups."""
    groups = defaultdict(list)
    for r in rows: groups[r[key]].append(r)
    for g in groups.values(): rng.shuffle(g)
    order = sorted(groups); rng.shuffle(order)
    picked = []
    while len(picked) < k and any(groups.values()):
        for g in order:
            if groups[g] and len(picked) < k: picked.append(groups[g].pop())
    return picked

by_risk = defaultdict(list)
for r in sorted(fpp, key=lambda r: r["path"]): by_risk[r["risk_id"]].append(r)
fpp_pick = [r for risk in sorted(by_risk) for r in spread(by_risk[risk], "task_id", fpp_k)]
if smp_k == "all":
    smp_pick = sorted(smp, key=lambda r: r["path"])
else:
    sb = defaultdict(list)
    for r in sorted(smp, key=lambda r: r["path"]): sb[r["risk_id"]].append(r)
    smp_pick = [r for risk in sorted(sb) for r in spread(sb[risk], "pair", int(smp_k))]

json.dump({"seed": 0, "fpp_per_risk": fpp_k, "smp_per_risk": smp_k,
           "fpp": fpp_pick, "smp": smp_pick}, open(f"{out}/sample_ids.json", "w"), indent=1)
with open(f"{out}/fpp_sample.tsv", "w") as f:
    f.write("# task\tslug\trisk\tsample_id\n")
    for r in fpp_pick: f.write(f"{r['task_id']}\t{r['target_slug']}\t{r['risk_id']}\t{r['sample_id']}\n")
print(f"FPP {len(fpp_pick)} samples over {len({r['task_id'] for r in fpp_pick})} tasks; SMP {len(smp_pick)}")
