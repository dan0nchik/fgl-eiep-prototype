#!/usr/bin/env python3
"""(run box) Collect per-trial outcomes for every condition into one JSON (no secrets: ids, flags, token usage).
usage: collect_outcomes.py OUT.json"""
import glob, json, os, re, sys
ROOT = os.path.expanduser("~/skillharm_run/SkillHarm/AutoSkillHarm")
VICTIM = os.environ.get("VICTIM_ID", "codex_gpt-5.6-luna")
def usage(path):
    u = None
    if path and os.path.isfile(path):
        for l in open(path, errors="replace"):
            if '"turn.completed"' in l:
                try: u = json.loads(l).get("usage")
                except Exception: pass
    return u
def injected(d):
    """True if the harbor job log shows the authors' AGENTS.md defense heredoc in the codex command."""
    j = os.path.realpath(os.path.join(d, "job"))
    for f in (os.path.join(j, "trial.log"), os.path.join(os.path.dirname(j), "job.log")):
        if os.path.isfile(f) and "SKILLHARM_DEFENSE_EOF" in open(f, errors="replace").read(): return True
    return False
def judge(d):
    p = os.path.join(d, "metrics_result.json")
    if not os.path.isfile(p): return None
    m = json.load(open(p)); return {k: m.get(k) for k in ("enter_entry_point", "use_target_file", "identified", "refusal", "error_kind")}
rows = []
for base, scn in (("results", "FPP"), ("benign", "BENIGN")):
    for d in glob.glob(f"{ROOT}/fixed-payload-poisoning/{base}/*/*/*/outputs/*/evals*/**/{VICTIM}/*/", recursive=True):
        parts = d.rstrip("/").split("/"); sid = parts[-1]
        cond = "none" if parts[-3] == "evals" else parts[-3]
        i = parts.index("outputs"); task, slug, risk = parts[i-3], parts[i-2], parts[i-1]
        asr = json.load(open(d + "asr_result.json")).get("asr_success") if os.path.isfile(d + "asr_result.json") else None
        rew = open(d + "reward.txt").read().strip() if os.path.isfile(d + "reward.txt") else None
        done = (asr is not None) if scn == "FPP" else (rew is not None)
        if not done: continue
        rows.append({"scenario": scn, "cond": cond, "id": sid, "task": task, "risk": risk if scn == "FPP" else None,
                     "attack_success": bool(asr) if scn == "FPP" else None, "task_reward": rew,
                     "usage": usage(d + "codex.txt"), "judge": judge(d),
                     "defense_injected": injected(d) if cond != "none" else None})
for d in glob.glob(f"{ROOT}/self-mutating-poisoning/task_pairs/*/*/eval*/**/runner_{VICTIM}/", recursive=True):
    if not os.path.isfile(d + "eval_result.json"): continue
    r = json.load(open(d + "eval_result.json")); parts = d.rstrip("/").split("/")
    cond = "none" if parts[-3] == "eval" else parts[-3]
    jobs = {}
    if os.path.isfile(d + "eval.log"):
        for l in open(d + "eval.log", errors="replace"):
            m = re.search(r"FGL_JOB_([AB]): (\S+)", l)
            if m: jobs[m.group(1)] = m.group(2)
    rows.append({"scenario": "SMP", "cond": cond, "id": f"{r['pair']}__{r['risk_type']}__{r['design_agent_id']}",
                 "task": r["pair"], "risk": r["risk_type"], "attack_success": bool(r.get("attack_successful")),
                 "task_reward": r.get("task_b_reward"), "task_a_reward": r.get("task_a_reward"),
                 "duration_sec": r.get("duration_sec"),
                 "usage": {ph: usage(os.path.join(j, "agent", "codex.txt")) for ph, j in jobs.items()},
                 "judge": judge(d)})
json.dump(rows, open(sys.argv[1], "w"), indent=1)
from collections import Counter
print(len(rows), Counter((r["scenario"], r["cond"]) for r in rows))
