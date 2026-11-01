#!/usr/bin/env python3
"""Export per-trial Codex trajectories of one condition into one JSON per trial (for offline monitor replay).
Secrets (proxy URL/host/credentials, API keys, ChatGPT tokens) are scrubbed from every string.
usage: export_trajectories.py COND(none|<slug>) OUT_DIR"""
import glob, json, os, re, sys, urllib.parse
ROOT = os.path.expanduser("~/skillharm_run/SkillHarm/AutoSkillHarm")
DATA = os.path.expanduser("~/skillharm_run/SkillHarm_data")
VICTIM = os.environ.get("VICTIM_ID", "codex_gpt-5.6-luna")
MAXOUT = 4000

def secrets():
    s = []
    try:
        p = open(os.path.expanduser("~/.openai_proxy")).read().strip(); u = urllib.parse.urlparse(p)
        s += [p, f"{u.hostname}:{u.port}" if u.port else u.hostname, u.hostname, u.username or "", u.password or ""]
    except Exception: pass
    try:
        a = json.load(open(os.path.expanduser("~/.codex_sub/auth.json")))
        s += [v for v in (a.get("tokens") or {}).values() if isinstance(v, str) and len(v) > 12]
    except Exception: pass
    for k in ("OPENAI_API_KEY",):
        try:
            for line in open(os.path.expanduser("~/skillharm_run/env")):
                m = re.match(rf'export {k}="?([^"\n]+)"?', line)
                if m and len(m.group(1)) > 12: s.append(m.group(1))
        except Exception: pass
    return sorted({x for x in s if x and len(x) >= 6}, key=len, reverse=True)
SECRETS = secrets()
GENERIC = re.compile(r"sk-[A-Za-z0-9_\-]{20,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")
def scrub(x):
    if isinstance(x, str):
        for s in SECRETS: x = x.replace(s, "<REDACTED>")
        return GENERIC.sub("<REDACTED>", x)
    if isinstance(x, list): return [scrub(v) for v in x]
    if isinstance(x, dict): return {k: scrub(v) for k, v in x.items()}
    return x

def parse_codex(path, phase=None):
    steps, usage = [], None
    if not path or not os.path.isfile(path): return steps, usage
    for line in open(path, errors="replace"):
        try: e = json.loads(line)
        except Exception: continue
        if e.get("type") == "turn.completed": usage = e.get("usage")
        if e.get("type") in ("error", "turn.failed"):
            msg = e.get("message") or (e.get("error") or {}).get("message", "")
            if "Model metadata" not in msg: steps.append({"type": "error", "text": msg})
            continue
        if e.get("type") != "item.completed": continue
        it = e["item"]; t = it.get("type"); st = None
        if t == "command_execution":
            out = it.get("aggregated_output") or ""
            st = {"type": "command", "command": it.get("command"), "exit_code": it.get("exit_code"),
                  "output": out[:MAXOUT] + ("...[truncated]" if len(out) > MAXOUT else "")}
        elif t in ("agent_message", "reasoning"):
            st = {"type": t, "text": it.get("text", "")}
        elif t == "file_change":
            st = {"type": "file_change", "text": json.dumps(it.get("changes")), "changes": it.get("changes")}
        elif t in ("mcp_tool_call", "web_search", "todo_list"):
            st = {"type": t, "text": json.dumps({k: v for k, v in it.items() if k not in ("id",)})[:MAXOUT]}
        if st:
            if phase: st["phase"] = phase
            steps.append(st)
    return steps, usage

def skill_of(target):
    m = re.match(r"environment/skills/([^/]+)/", target or ""); return m.group(1) if m else None

def main():
    cond, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
    idx = {r["sample_id"]: r for r in map(json.loads, open(f"{DATA}/fpp_index.jsonl"))}
    n = 0
    for scn, base in (("FPP", "results"), ("BENIGN", "benign")):
        sub = f"evals/{VICTIM}" if cond == "none" else f"evals_defense/{cond}/{VICTIM}"
        for d in sorted(glob.glob(f"{ROOT}/fixed-payload-poisoning/{base}/*/*/*/outputs/*/{sub}/*/")):
            sid = os.path.basename(d.rstrip("/")); task = d.split(f"/{base}/")[1].split("/")[0]
            done_marker = "asr_result.json" if scn == "FPP" else "reward.txt"
            if not os.path.isfile(os.path.join(d, done_marker)): continue   # in progress / aborted
            steps, usage = parse_codex(os.path.join(d, "codex.txt"))
            asr = None
            if os.path.isfile(os.path.join(d, "asr_result.json")):
                asr = bool(json.load(open(os.path.join(d, "asr_result.json"))).get("asr_success"))
            reward = open(os.path.join(d, "reward.txt")).read().strip() if os.path.isfile(os.path.join(d, "reward.txt")) else None
            meta = idx.get(sid, {})
            inst_p = os.path.join(d, "job")  # instruction from the sample dir
            sample_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(d.rstrip("/")))), "samples", sid)
            instr = open(os.path.join(sample_dir, "instruction.md")).read() if os.path.isfile(os.path.join(sample_dir, "instruction.md")) else None
            rec = {"id": sid if scn == "FPP" else f"benign__{task}", "scenario": scn, "condition": cond,
                   "risk": meta.get("risk_id") if scn == "FPP" else None, "task": task,
                   "skill": skill_of(meta.get("target_path")) if scn == "FPP" else None,
                   "carrier_path": meta.get("target_path"), "realization": meta.get("realization"),
                   "instruction": instr, "victim": VICTIM, "steps": steps,
                   "harmful_outcome": bool(asr) if scn == "FPP" else False,
                   "asr_result_present": asr is not None, "task_reward": reward, "usage": usage}
            json.dump(scrub(rec), open(os.path.join(out, f"{scn.lower()}__{rec['id']}.json"), "w"), indent=1); n += 1
    sub = "eval" if cond == "none" else f"eval_defense/{cond}"
    for d in sorted(glob.glob(f"{ROOT}/self-mutating-poisoning/task_pairs/*/*/{sub}/designer_*/runner_{VICTIM}/")):
        er = os.path.join(d, "eval_result.json")
        if not os.path.isfile(er): continue
        r = json.load(open(er)); pair, risk = r["pair"], r["risk_type"]
        jobs = {}
        for line in open(os.path.join(d, "eval.log"), errors="replace"):
            m = re.search(r"FGL_JOB_([AB]): (\S+)", line)
            if m: jobs[m.group(1)] = m.group(2)
        steps = []; usage = {}
        for ph in ("A", "B"):
            s, u = parse_codex(os.path.join(jobs.get(ph, "/nonexistent"), "agent", "codex.txt"), phase=f"task_{ph.lower()}")
            steps += s; usage[ph] = u
        design_dir = os.path.join(ROOT, "self-mutating-poisoning/task_pairs", pair, risk, "outputs", r["design_agent_id"])
        skills = sorted(os.listdir(os.path.join(design_dir, "modified_skills"))) if os.path.isdir(os.path.join(design_dir, "modified_skills")) else []
        ins = {}
        for ph in ("a", "b"):
            p = os.path.join(ROOT, "self-mutating-poisoning/task_pairs", pair, f"task_{ph}", "instruction.md")
            ins[ph] = open(p).read() if os.path.isfile(p) else None
        sid = f"{pair}__{risk}__{r['design_agent_id']}"
        rec = {"id": sid, "scenario": "SMP", "condition": cond, "risk": risk, "task": pair,
               "skill": ",".join(skills), "instruction": ins, "victim": VICTIM, "steps": steps,
               "harmful_outcome": bool(r.get("attack_successful")),
               "task_a_reward": r.get("task_a_reward"), "task_b_reward": r.get("task_b_reward"),
               "detection_passed": r.get("detection_passed"), "detection_failed": r.get("detection_failed"),
               "usage": usage}
        json.dump(scrub(rec), open(os.path.join(out, f"smp__{sid}.json"), "w"), indent=1); n += 1
    # final guard: no secret may survive
    for f in glob.glob(os.path.join(out, "*.json")):
        txt = open(f).read()
        assert not any(s in txt for s in SECRETS), f"secret leaked into {f}"
    print(f"exported {n} trajectories to {out}")
main()
