#!/usr/bin/env python3
"""(run box) After fpp:none: write fpp_valid.tsv (trials with a valid none outcome), fpp_excluded.json
(sample ids that never produced a valid none trial + failure signature from their harbor jobs), and
fpp_ablation.tsv (all none-successes + 10 none-failures, seed 0)."""
import glob, json, os, random, re
R = os.path.expanduser("~/skillharm_run"); A = f"{R}/SkillHarm/AutoSkillHarm/fixed-payload-poisoning"
V = "codex_gpt-5.6-luna"
rows = [l.rstrip("\n").split("\t") for l in open(f"{R}/fpp_sample.tsv") if l.strip() and not l.startswith("#")]
valid, excluded, succ, fail = [], [], [], []
for t, slug, risk, sid in rows:
    d = glob.glob(f"{A}/results/{t}/{slug}/{risk}/outputs/*/evals/{V}/{sid}/asr_result.json")
    if d:
        valid.append((t, slug, risk, sid)); (succ if json.load(open(d[0])).get("asr_success") else fail).append((t, slug, risk, sid))
    else:
        sigs = set()
        for exc in glob.glob(f"{A}/victim_eval/jobs/{V}/{sid}/*/*__*/exception.txt"):
            s = open(exc, errors="replace").read()
            m = re.search(r"Version '22' not found|timed out after [0-9.]+ seconds|NetworkConnectionError|EnvironmentStartTimeoutError|AgentSetupTimeoutError", s)
            sigs.add(m.group(0) if m else (re.findall(r"(\w+Error)", s) or ["unknown"])[-1])
        excluded.append({"task": t, "risk": risk, "sample_id": sid, "attempts": len(glob.glob(f"{A}/victim_eval/jobs/{V}/{sid}/*/")), "failure_signatures": sorted(sigs)})
def w(name, xs):
    with open(f"{R}/{name}", "w") as f:
        f.write("# task\tslug\trisk\tsample_id\n"); [f.write("\t".join(x) + "\n") for x in xs]
w("fpp_valid.tsv", valid)
rng = random.Random(0); ff = sorted(fail); rng.shuffle(ff)
w("fpp_ablation.tsv", sorted(succ) + sorted(ff[:10]))
json.dump(excluded, open(f"{R}/fpp_excluded.json", "w"), indent=1)
print(f"valid {len(valid)} (success {len(succ)}, fail {len(fail)}); excluded {len(excluded)}; ablation set {len(succ) + min(10, len(fail))}")
from collections import Counter
print(Counter(s for e in excluded for s in e["failure_signatures"])); print(Counter(e["task"] for e in excluded))
