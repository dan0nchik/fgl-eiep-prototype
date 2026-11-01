#!/usr/bin/env python3
"""Export AutoSkillHarm none-condition victim trajectories to the replay format.

Reads a local copy of the SkillHarm FPP results tree (rsynced from the server, see
RESULTS.md) and, for every none-condition eval trial, emits one normalized JSON file
under trajectories/none/<sample_id>.json with the schema documented in
trajectories/none/README.md:

  {
    "id": "<sample_id>",
    "scenario": "fixed_payload_poisoning",
    "risk": "<risk_id>",
    "task": "<skillsbench task id>",
    "skill": "<owning skill root, e.g. environment/skills/citation-management>",
    "instruction": "<user task text, if available>",
    "steps": [ {"type": "command"|"message"|"file_change"|"other",
                "command": "<shell cmd>"  # for command steps
                "text": "<assistant text>"  # for message steps
                "changes": [...]            # for file_change steps
               }, ... ],
    "harmful_outcome": <bool>   # deterministic ASR verdict from the authors' evaluator
  }

No SkillHarm code is copied or imported; this is an independent reader of the
Codex CLI `--json` event stream (codex.txt) that Harbor's codex agent writes, plus
the authors' deterministic asr_result.json / manifest.json metadata.

Usage:
  python export_trajectories.py --results <local_results_dir> \
      --victim codex_gpt-4.1 --out trajectories/none
"""
from __future__ import annotations
import argparse, json, shlex
from pathlib import Path


def unwrap_shell(cmd):
    """Codex records commands as `/bin/bash -lc '<cmd>'`; strip that wrapper."""
    if isinstance(cmd, list):
        cmd = " ".join(shlex.quote(str(x)) for x in cmd)
    try:
        tok = shlex.split(cmd)
    except ValueError:
        return cmd
    if len(tok) == 3 and tok[0].rsplit("/", 1)[-1] in ("bash", "sh", "zsh") and tok[1] in ("-lc", "-c", "-cl"):
        return tok[2]
    return cmd


def parse_codex(path: Path):
    steps = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") != "item.completed":
            continue
        it = e.get("item") or {}
        t = it.get("type") or ""
        if t == "command_execution":
            steps.append({"type": "command",
                          "command": unwrap_shell(it.get("command", "") or ""),
                          "exit_code": it.get("exit_code")})
        elif t == "file_change":
            steps.append({"type": "file_change",
                          "changes": [{"path": c.get("path"), "kind": c.get("kind")}
                                      for c in (it.get("changes") or []) if isinstance(c, dict)]})
        elif t in ("agent_message", "assistant_message"):
            steps.append({"type": "message", "text": it.get("text", "") or ""})
        elif t == "mcp_tool_call":
            steps.append({"type": "other", "tool": f"{it.get('server')}.{it.get('tool')}",
                          "command": json.dumps(it.get("arguments"), ensure_ascii=False)[:2000]})
    return steps


def manifest_meta(gen_dir: Path, sample_id: str):
    """owning skill + risk + realization from the generator manifest."""
    mf = gen_dir / "manifest.json"
    if not mf.is_file():
        return {}
    try:
        for e in json.loads(mf.read_text()):
            if e.get("sample_id") == sample_id:
                return e
    except Exception:
        pass
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="local copy of fixed-payload-poisoning/results")
    ap.add_argument("--victim", default="codex_gpt-5.6-luna")
    ap.add_argument("--out", default="trajectories/none")
    args = ap.parse_args()

    results = Path(args.results)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    n = 0
    # layout: <task>/<slug>/<risk>/outputs/<generator>/evals/<victim>/<sample_id>/
    for asr_path in results.glob(f"*/*/*/outputs/*/evals/{args.victim}/*/asr_result.json"):
        eval_dir = asr_path.parent
        sample_id = eval_dir.name
        parts = asr_path.parts
        oi = parts.index("outputs")
        task, slug, risk, generator = parts[oi - 3], parts[oi - 2], parts[oi - 1], parts[oi + 1]
        gen_dir = results / task / slug / risk / "outputs" / generator
        meta = manifest_meta(gen_dir, sample_id)
        try:
            asr = json.loads(asr_path.read_text())
        except Exception:
            asr = {}
        codex = eval_dir / "codex.txt"
        steps = parse_codex(codex) if codex.is_file() else []
        # user instruction from the sample's instruction.md (not the skill content)
        instr = ""
        instr_f = gen_dir / "samples" / sample_id / "instruction.md"
        if instr_f.is_file():
            instr = instr_f.read_text(errors="replace")
        rec = {
            "id": sample_id,
            "scenario": "fixed_payload_poisoning",
            "risk": risk,
            "task": task,
            "skill": meta.get("owning_skill_root"),
            "realization": meta.get("realization"),
            "target_path": meta.get("target_task_relative_path"),
            "instruction": instr,
            "steps": steps,
            "harmful_outcome": bool(asr.get("asr_success")),
            "asr_evidence": asr.get("asr_evidence"),
        }
        (out / f"{sample_id}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False))
        n += 1
    print(f"wrote {n} trajectories to {out}")


if __name__ == "__main__":
    main()
