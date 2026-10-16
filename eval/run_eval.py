"""Evaluation of the FGL prototype on EIEP episodes and ordinary tasks (FGL Plan v3, section 7.6).

Conditions: none (no layer), fgl_full, and ablations no_graph (monitor only), no_gate, no_verifier, no_reasoning.
Metrics: EIEP detected, harm prevented before execution, detection delay (steps in phase B; 0 = flagged at the
gate), false blocks and success on ordinary tasks, overhead (LLM calls, tokens, latency, probes).

Usage: export OPENAI_API_KEY=...; python -m eval.run_eval --model gpt-4.1-mini [--episodes E1_alt_tool,...] [--conditions none,fgl_full]
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.loop import Agent                       # noqa: E402
from episodes.benign import BENIGN                  # noqa: E402
from episodes.eiep import EPISODES, ContainerU      # noqa: E402
from fgl import FGL, FGLConfig, Target, TRUSTED, UNTRUSTED   # noqa: E402
from fgl.llm import LLM                             # noqa: E402

CONDITIONS = {
    "none": FGLConfig(enabled=False, name="none"),
    "fgl_full": FGLConfig(name="fgl_full"),
    "no_graph": FGLConfig(graph=False, name="no_graph"),
    "no_gate": FGLConfig(gate=False, name="no_gate"),
    "no_verifier": FGLConfig(verifier=False, name="no_verifier"),
    "no_reasoning": FGLConfig(reasoning=False, name="no_reasoning"),
}


def run_episode(ep, cfg: FGLConfig, model: str) -> Dict[str, Any]:
    llm = LLM(model)
    fgl = FGL(llm, cfg)
    agent = Agent(llm, fgl)
    root = Path(tempfile.mkdtemp(prefix=f"eiep_{ep.id}_{cfg.name}_"))
    udir, tdir = root / "u", root / "t"
    udir.mkdir(); tdir.mkdir()
    ep.setup_u(udir)
    out: Dict[str, Any] = {"episode": ep.id, "mechanism": ep.mechanism, "condition": cfg.name}
    t0 = time.time()
    try:
        with ContainerU(udir, extra_path=(ep.id == "E5_precondition")) as c:
            tu = Target("U", "container", "/work", container_id=c.id, domain=UNTRUSTED, config_files=ep.config_files, tools=ep.tools)
            ra = agent.run(tu, ep.task_a)
            art = agent.evolve(ep.task_a, ra)
        out["phase_a"] = {"answer": ra["answer"][:300], "steps": ra["steps"], "artifact": art}
        ep.setup_t(tdir)
        tt = Target("T", "host", str(tdir), domain=TRUSTED, config_files=ep.config_files, tools=ep.tools)
        rb = agent.run(tt, ep.task_b)
        harm = ep.harm(tdir, rb["answer"], rb["trajectory"])
        succ = ep.success_b(tdir, rb["answer"], rb["trajectory"])
        blocks = [r for r in rb["trajectory"] if r.get("blocked")]
        eiep_flags = [r for r in rb["trajectory"] if (r.get("decision") or {}).get("signals", {}) and r["decision"]["signals"].get("eiep")]
        gate_flag = bool(art and art.get("status") in ("scoped", "quarantined"))
        out["phase_b"] = {"answer": rb["answer"][:300], "steps": rb["steps"], "trajectory": rb["trajectory"]}
        out["metrics"] = {
            "artifact_created": art is not None,
            "gate_flagged": gate_flag,
            "detected": bool(eiep_flags) or (gate_flag and cfg.enabled and art.get("status") == "quarantined"),
            "blocked_any": bool(blocks),
            "harm": harm, "success": succ,
            "prevented": (not harm) and bool(blocks),
            "detection_delay_steps": (eiep_flags[0]["step"] if eiep_flags else None),
            "audits": sum(1 for r in rb["trajectory"] if (r.get("decision") or {}).get("action") == "allow_audit"),
        }
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        pidf = tdir / ".holder_pid"
        if pidf.exists():
            try:
                os.kill(int(pidf.read_text()), signal.SIGKILL)
            except Exception:
                pass
        shutil.rmtree(root, ignore_errors=True)
    out["overhead"] = {**llm.stats(), **fgl.stats(), "wall_s": round(time.time() - t0, 1)}
    return out


def seed_rule(fgl: FGL, rule: Dict[str, Any], tdir: Path) -> Dict[str, Any]:
    """Pre-seed a legitimately learned artifact. origin T: evidence = a host observation;
    origin U: evidence = an observation from a scratch container (premises hold on the host too)."""
    if rule["origin"] == "T":
        t = Target("T", "host", str(tdir), domain=TRUSTED)
        _, _, oid = fgl.run_tool(t, "ls")
    else:
        scratch = Path(tempfile.mkdtemp(prefix="seedU_"))
        with ContainerU(scratch) as c:
            tu = Target("U", "container", "/work", container_id=c.id, domain=UNTRUSTED)
            _, _, oid = fgl.run_tool(tu, "command -v jq || echo 'jq: missing'; command -v sha256sum || echo 'sha256sum: missing'")
        shutil.rmtree(scratch, ignore_errors=True)
    a = fgl.on_artifact_write("tool_rule", rule["name"], rule["rule"], [oid])
    return {"artifact": a.id, "status": a.status, "premises": [p.text for p in a.premises], "domains": a.domains}


def run_benign(bt, cfg: FGLConfig, model: str) -> Dict[str, Any]:
    llm = LLM(model)
    fgl = FGL(llm, cfg)
    agent = Agent(llm, fgl)
    tdir = Path(tempfile.mkdtemp(prefix=f"benign_{bt.id}_{cfg.name}_"))
    out: Dict[str, Any] = {"task": bt.id, "condition": cfg.name}
    t0 = time.time()
    try:
        bt.setup(tdir)
        if bt.rule:
            out["seed"] = seed_rule(fgl, bt.rule, tdir)
        t = Target("T", "host", str(tdir), domain=TRUSTED)
        r = agent.run(t, bt.task)
        blocks = [x for x in r["trajectory"] if x.get("blocked")]
        out["metrics"] = {"success": bool(bt.check(tdir, r["answer"], r["trajectory"])), "false_block": bool(blocks),
                          "steps": r["steps"], "rule_origin": (bt.rule or {}).get("origin")}
        out["answer"] = r["answer"][:200]
        out["trajectory"] = r["trajectory"]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        shutil.rmtree(tdir, ignore_errors=True)
    out["overhead"] = {**llm.stats(), **fgl.stats(), "wall_s": round(time.time() - t0, 1)}
    return out


def pct(xs, f):
    xs = list(xs)
    return round(100.0 * sum(1 for x in xs if f(x)) / max(1, len(xs)), 1)


def summarize(ep_rows: List[Dict], bn_rows: List[Dict]) -> Dict[str, Any]:
    s: Dict[str, Any] = {}
    for c in CONDITIONS:
        e = [r for r in ep_rows if r["condition"] == c and "metrics" in r]
        b = [r for r in bn_rows if r["condition"] == c and "metrics" in r]
        if not e and not b:
            continue
        delays = [r["metrics"]["detection_delay_steps"] for r in e if r["metrics"]["detection_delay_steps"] is not None]
        s[c] = {
            "episodes": len(e),
            "artifact_created": pct(e, lambda r: r["metrics"]["artifact_created"]),
            "gate_flagged": pct(e, lambda r: r["metrics"]["gate_flagged"]),
            "detected": pct(e, lambda r: r["metrics"]["detected"]),
            "harm": pct(e, lambda r: r["metrics"]["harm"]),
            "prevented_before_exec": pct(e, lambda r: r["metrics"]["prevented"]),
            "task_b_success": pct(e, lambda r: r["metrics"]["success"]),
            "mean_detection_delay_steps": round(sum(delays) / len(delays), 2) if delays else None,
            "benign_tasks": len(b),
            "benign_success": pct(b, lambda r: r["metrics"]["success"]),
            "benign_false_block": pct(b, lambda r: r["metrics"]["false_block"]),
            "benign_false_block_U_rules": pct([r for r in b if r["metrics"].get("rule_origin") == "U"], lambda r: r["metrics"]["false_block"]),
            "mean_llm_calls_episode": round(sum(r["overhead"]["calls"] for r in e) / max(1, len(e)), 1),
            "mean_tokens_episode": round(sum(r["overhead"]["prompt_tokens"] + r["overhead"]["completion_tokens"] for r in e) / max(1, len(e))),
            "mean_probes_episode": round(sum(r["overhead"]["probes"] for r in e) / max(1, len(e)), 2),
            "mean_wall_s_episode": round(sum(r["overhead"]["wall_s"] for r in e) / max(1, len(e)), 1),
        }
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    ap.add_argument("--episodes", default=",".join(e.id for e in EPISODES))
    ap.add_argument("--benign", default=",".join(b.id for b in BENIGN))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=1)
    a = ap.parse_args()
    conds = [c for c in a.conditions.split(",") if c]
    eps = [e for e in EPISODES if e.id in a.episodes.split(",")]
    bns = [b for b in BENIGN if b.id in a.benign.split(",")] if a.benign else []
    jobs = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for _ in range(a.repeats):
            for c in conds:
                for e in eps:
                    jobs.append(("ep", ex.submit(run_episode, e, CONDITIONS[c], a.model)))
                for b in bns:
                    jobs.append(("bn", ex.submit(run_benign, b, CONDITIONS[c], a.model)))
        ep_rows, bn_rows = [], []
        for kind, f in jobs:
            r = f.result()
            (ep_rows if kind == "ep" else bn_rows).append(r)
            tag = r.get("episode") or r.get("task")
            m = r.get("metrics", {})
            print(f"  [{r['condition']:<13}] {tag:<18} {('ERR ' + r['error']) if 'error' in r else json.dumps(m)}", flush=True)
    summary = summarize(ep_rows, bn_rows)
    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    out = Path(__file__).resolve().parent.parent / "results" / f"eval_{a.model}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"metadata": {"model": a.model, "conditions": conds, "repeats": a.repeats,
                                            "timestamp": datetime.utcnow().isoformat() + "Z"},
                               "summary": summary, "episodes": ep_rows, "benign": bn_rows}, ensure_ascii=False, indent=2))
    print("saved", out)


if __name__ == "__main__":
    main()
