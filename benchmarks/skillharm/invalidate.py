#!/usr/bin/env python3
"""Find trials that failed for infrastructure / API reasons (quota, auth, proxy, network, harbor abort) and
move them out of the results tree so the authors' resume logic re-runs them. Such trials are NEVER counted
as "attack failed". Agent-side failures that are not infra (e.g. context length) are kept and logged.
usage: invalidate.py SCENARIO(fpp|benign|smp) COND(none|<defense_slug>) [--apply]"""
import glob, json, os, re, shutil, sys, time
ROOT = os.path.expanduser("~/skillharm_run/SkillHarm/AutoSkillHarm")
INV = os.path.expanduser("~/skillharm_run/invalid")
VICTIM = os.environ.get("VICTIM_ID", "codex_gpt-5.6-luna")
INFRA = re.compile(r"quota|credit|insufficient|rate.?limit|\b429\b|\b401\b|\b403\b|unauthori[sz]ed|"
                   r"stream disconnected|error sending request|connection|timed? ?out|proxy|"
                   r"usage limit|too many requests|unexpected status|service unavailable|\b50[0234]\b|overloaded|reconnecting", re.I)

def codex_status(path):
    """-> ('ok'|'infra'|'missing'|'agent_error', detail)"""
    if not path or not os.path.isfile(path): return "missing", "no codex.txt"
    started = False; errs = []
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line.startswith("{"): continue
        try: ev = json.loads(line)
        except Exception: continue
        t = ev.get("type")
        if t == "turn.started": started = True
        if t in ("error", "turn.failed"):
            msg = ev.get("message") or (ev.get("error") or {}).get("message", "")
            if "Model metadata" in msg: continue   # benign codex warning for non-catalog models
            errs.append(msg)
    infra = [e for e in errs if INFRA.search(e)]
    if infra: return "infra", infra[0][:200]
    if not started: return "missing", "agent never started a turn"
    if errs: return "agent_error", errs[0][:200]
    return "ok", ""

def fpp_dirs(scn, cond):
    base = "results" if scn == "fpp" else "benign"
    sub = f"evals/{VICTIM}" if cond == "none" else f"evals_defense/{cond}/{VICTIM}"
    return glob.glob(f"{ROOT}/fixed-payload-poisoning/{base}/*/*/*/outputs/*/{sub}/*/")

def smp_dirs(cond):
    sub = "eval" if cond == "none" else f"eval_defense/{cond}"
    return glob.glob(f"{ROOT}/self-mutating-poisoning/task_pairs/*/*/{sub}/designer_*/runner_{VICTIM}/")

def smp_jobs(d):
    jobs = {}
    log = os.path.join(d, "eval.log")
    if os.path.isfile(log):
        for line in open(log, errors="replace"):
            m = re.search(r"FGL_JOB_([AB]): (\S+)", line)
            if m: jobs[m.group(1)] = m.group(2)   # last attempt wins
    return jobs

def main():
    scn, cond = sys.argv[1], sys.argv[2]; apply = "--apply" in sys.argv
    stamp = time.strftime("%Y%m%d_%H%M%S"); report = {"valid": 0, "invalid": [], "agent_error": []}
    if scn in ("fpp", "benign"):
        for d in fpp_dirs(scn, cond):
            st, det = codex_status(os.path.join(d, "codex.txt"))
            aborted = os.path.isfile(os.path.join(d, "aborted.json"))
            # benign tasks have no ASR evaluator -> aborted.json is expected; judge by reward.txt instead
            if scn == "benign": aborted = not os.path.isfile(os.path.join(d, "reward.txt"))
            bad = st in ("infra", "missing") or aborted
            if st == "agent_error": report["agent_error"].append((d, det))
            if bad: report["invalid"].append((d, st if st != "ok" else "harbor_aborted", det))
            else: report["valid"] += 1
    else:
        for d in smp_dirs(cond):
            er = os.path.join(d, "eval_result.json")
            if not os.path.isfile(er): continue
            r = json.load(open(er)); jobs = smp_jobs(d); why = None
            for ph in ("A", "B"):
                st, det = codex_status(os.path.join(jobs.get(ph, ""), "agent", "codex.txt") if jobs.get(ph) else None)
                if st in ("infra", "missing"): why = (f"task_{ph}:{st}", det); break
                if st == "agent_error": report["agent_error"].append((d, f"{ph}: {det}"))
            if not why and (r.get("task_a_reward") == "?" or r.get("task_b_reward") == "?"):
                why = ("reward_missing", f"rA={r.get('task_a_reward')} rB={r.get('task_b_reward')}")
            if why: report["invalid"].append((d, *why))
            else: report["valid"] += 1
    for d, *why in report["invalid"]:
        if apply:
            dst = os.path.join(INV, stamp, os.path.relpath(d.rstrip("/"), ROOT))
            os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.move(d.rstrip("/"), dst)
    print(json.dumps({"scenario": scn, "cond": cond, "valid": report["valid"],
                      "invalid": len(report["invalid"]),
                      "invalid_reasons": sorted({w[0] for _, *w in report["invalid"]}),
                      "quota_hit": any("quota" in (w[1] or "").lower() or "credit" in (w[1] or "").lower()
                                       for _, *w in report["invalid"]),
                      "agent_errors": len(report["agent_error"]), "applied": apply}))
    if apply and report["invalid"]:
        with open(os.path.expanduser("~/skillharm_run/logs/invalidated.jsonl"), "a") as f:
            for d, *w in report["invalid"]:
                f.write(json.dumps({"t": stamp, "scn": scn, "cond": cond, "dir": d, "why": w}) + "\n")
main()
