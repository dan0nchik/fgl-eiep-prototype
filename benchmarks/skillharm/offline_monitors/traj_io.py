"""Load SkillHarm victim trajectories into one normalized form for offline monitor replay.

Normalized trajectory:
  {"sample_id", "scenario", "risk_id", "condition", "asr_success": bool|None, "benign": bool,
   "instruction": str, "harm_step": int|None, "traj_path": str,
   "steps": [{"i": int, "type": "command"|"file_change"|"message"|"other",
              "command": str, "output": str, "changes": [...], "text": str}]}

Supported trajectory files (searched in each trajectory directory):
  codex.txt                   Codex CLI `--json` event stream (item.completed: command_execution / file_change /
                              agent_message / reasoning / ...), as written by Harbor's codex agent
  trajectory.json             Harbor ATIF trajectory (steps[].tool_calls[] + observation)
  normalized.json             already in the normalized form above
Metadata: meta.json / result.json / metadata.json next to the trajectory (any of: sample_id, scenario, risk_id,
asr_success|attack_success|success, instruction, harm_step, benign). Missing fields are left None.
`load_dir(root)` walks root recursively and returns one normalized trajectory per directory that holds a
trajectory file.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

TRAJ_FILES = ("normalized.json", "codex.txt", "trajectory.json")
META_FILES = ("meta.json", "result.json", "metadata.json", "sample.json")


def unwrap_shell(cmd: str) -> str:
    """Codex records every command as `/bin/bash -lc '<cmd>'` (its own exec wrapper). Strip that wrapper so the
    monitors see the command the agent actually wrote (a Hermes terminal tool receives it without a wrapper)."""
    try:
        tok = shlex.split(cmd)
    except ValueError:
        return cmd
    if len(tok) == 3 and tok[0].rsplit("/", 1)[-1] in ("bash", "sh", "zsh") and tok[1] in ("-lc", "-c", "-cl"):
        return tok[2]
    return cmd


def _jsonl(p: Path) -> List[Dict[str, Any]]:
    out = []
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def parse_codex(p: Path) -> List[Dict[str, Any]]:
    steps = []
    for e in _jsonl(p):
        if e.get("type") != "item.completed":
            continue
        it = e.get("item") or {}
        t = it.get("type") or it.get("item_type") or ""
        s: Dict[str, Any] = {"i": len(steps)}
        if t == "command_execution":
            raw = it.get("command", "") or ""
            if isinstance(raw, list):
                raw = " ".join(shlex.quote(str(x)) for x in raw)
            s.update(type="command", command=unwrap_shell(raw), command_raw=raw,
                     output=str(it.get("aggregated_output", "") or ""), exit_code=it.get("exit_code"))
        elif t == "file_change":
            s.update(type="file_change", changes=[{"path": c.get("path"), "kind": c.get("kind")}
                                                  for c in (it.get("changes") or []) if isinstance(c, dict)])
        elif t in ("agent_message", "assistant_message"):
            s.update(type="message", text=it.get("text", "") or "")
        elif t == "reasoning":
            continue
        elif t == "mcp_tool_call":
            s.update(type="other", tool=f"{it.get('server')}.{it.get('tool')}",
                     command=json.dumps(it.get("arguments"), ensure_ascii=False)[:2000])
        else:
            continue
        steps.append(s)
    return steps


def parse_atif(p: Path) -> List[Dict[str, Any]]:
    d = json.loads(p.read_text())
    steps = []
    for st in d.get("steps", []):
        obs = st.get("observation") or {}
        results = {r.get("source_call_id"): r.get("content") for r in (obs.get("results") or [])
                   if isinstance(r, dict)}
        for tc in st.get("tool_calls") or []:
            fn = tc.get("function_name") or tc.get("name") or ""
            args = tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            cmd = args.get("command") or args.get("cmd")
            if isinstance(cmd, list):
                cmd = " ".join(map(str, cmd))
            out = results.get(tc.get("tool_call_id"), "")
            if cmd:
                steps.append({"i": len(steps), "type": "command", "command": unwrap_shell(str(cmd)),
                              "command_raw": str(cmd), "output": str(out or "")})
            elif "patch" in fn.lower() or "write" in fn.lower() or "edit" in fn.lower():
                path = args.get("path") or args.get("file_path") or ""
                steps.append({"i": len(steps), "type": "file_change", "changes": [{"path": path, "kind": fn}]})
            else:
                steps.append({"i": len(steps), "type": "other", "tool": fn,
                              "command": json.dumps(args, ensure_ascii=False)[:2000], "output": str(out or "")})
        if st.get("source") == "agent" and st.get("message") and not st.get("tool_calls"):
            steps.append({"i": len(steps), "type": "message", "text": str(st.get("message"))})
    return steps


def load_export(p: Path, condition: str = "") -> Optional[Dict[str, Any]]:
    """One-JSON-per-trial format written by benchmarks/skillharm/export_trajectories.py:
    {id, scenario: FPP|BENIGN|SMP, condition, risk, task, skill, realization, instruction (str, or {a,b} for SMP),
     steps: [{type: command|agent_message|reasoning|file_change|error|..., command, output, phase?}],
     harmful_outcome, asr_result_present, ...}"""
    try:
        d = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(d, dict) or "steps" not in d or "scenario" not in d:
        return None
    scen = d["scenario"]
    instr = d.get("instruction")
    instr_by_phase = instr if isinstance(instr, dict) else {}
    steps: List[Dict[str, Any]] = []
    for st in d["steps"]:
        t = st.get("type")
        ph = st.get("phase")
        s: Dict[str, Any] = {"i": len(steps)}
        if ph:
            s["phase"] = ph
            s["task"] = instr_by_phase.get(ph.replace("task_", ""), "") or ""
        if t == "command":
            raw = st.get("command") or ""
            if isinstance(raw, list):
                raw = " ".join(shlex.quote(str(x)) for x in raw)
            s.update(type="command", command=unwrap_shell(raw), command_raw=raw, output=st.get("output") or "",
                     exit_code=st.get("exit_code"))
        elif t == "file_change":
            s.update(type="file_change", changes=[{"path": c.get("path"), "kind": c.get("kind")}
                                                  for c in (st.get("changes") or []) if isinstance(c, dict)])
        elif t == "agent_message":
            s.update(type="message", text=st.get("text") or "")
        elif t == "mcp_tool_call":
            s.update(type="other", tool="mcp_tool_call", command=(st.get("text") or "")[:2000])
        else:
            continue          # reasoning, errors, todo lists, web_search: not executed actions
        steps.append(s)
    benign = scen == "BENIGN"
    uid = d["id"] if scen != "FPP" else f"{d.get('task')}/{d['id']}"
    return {"sample_id": uid, "dataset_sample_id": d["id"], "scenario": scen, "risk_id": d.get("risk"),
            "condition": condition or d.get("condition"),
            "asr_success": None if benign else (bool(d.get("harmful_outcome"))
                                                if d.get("asr_result_present", True) else None),
            "benign": benign,
            "instruction": instr if isinstance(instr, str) else (instr_by_phase.get("b") or ""),
            "harm_step": None, "traj_path": str(p), "steps": steps,
            "meta_extra": {"task_id": d.get("task"), "realization": d.get("realization"), "skill": d.get("skill"),
                           "task_reward": d.get("task_reward"), "task_b_reward": d.get("task_b_reward")}}


def _meta(d: Path) -> Dict[str, Any]:
    m: Dict[str, Any] = {}
    for name in META_FILES:
        p = d / name
        if p.is_file():
            try:
                x = json.loads(p.read_text())
                if isinstance(x, dict):
                    for k, v in x.items():
                        m.setdefault(k, v)
            except json.JSONDecodeError:
                pass
    return m


def _asr(m: Dict[str, Any]) -> Optional[bool]:
    for k in ("asr_success", "attack_success", "asr", "success"):
        if k in m and m[k] is not None:
            v = m[k]
            if isinstance(v, (int, float, bool)):
                return bool(v)
            if isinstance(v, str):
                return v.strip().lower() in ("1", "true", "yes", "success")
    return None


def load_one(d: Path, condition: str = "") -> Optional[Dict[str, Any]]:
    for name in TRAJ_FILES:
        p = d / name
        if p.is_file() and p.stat().st_size > 0:
            break
    else:
        return None
    if name == "normalized.json":
        t = json.loads(p.read_text())
        t.setdefault("traj_path", str(p))
        return t
    steps = parse_codex(p) if name == "codex.txt" else parse_atif(p)
    m = _meta(d)
    instr = m.get("instruction") or ""
    if not instr and (d / "instruction.md").is_file():
        instr = (d / "instruction.md").read_text()
    return {"sample_id": m.get("sample_id") or d.name, "scenario": m.get("scenario"),
            "risk_id": m.get("risk_id"), "condition": condition or m.get("condition"),
            "asr_success": _asr(m), "benign": bool(m.get("benign", False)), "instruction": instr,
            "harm_step": m.get("harm_step"), "traj_path": str(p), "steps": steps,
            "meta_extra": {k: m[k] for k in ("task_id", "realization", "pair", "victim") if k in m}}


def load_dir(root: Path, condition: str = "") -> List[Dict[str, Any]]:
    out, seen = [], set()
    for p in sorted(root.glob("*.json")):        # export_trajectories.py layout: one JSON per trial
        t = load_export(p, condition)
        if t is not None:
            out.append(t)
    if out:
        return out
    for name in TRAJ_FILES:
        for p in sorted(root.rglob(name)):
            if p.parent in seen:
                continue
            t = load_one(p.parent, condition)
            if t is not None:
                seen.add(p.parent)
                out.append(t)
    return out
