"""SMP (self-mutating poisoning) sample enumeration for the static scans.

Each SMP sample ships `modified_skills/<skill>/...` = the stage-1 (as-installed) poisoned skill package(s): an
innocuous-looking skill whose script installs an atexit hook that rewrites sibling skill files when Task A exits.
The stage-2 (mutated) content is produced only at runtime by that hook; the dataset does not ship it as files,
so `stage2_dirs` is filled only if a runtime snapshot directory is provided (SMP_STAGE2_ROOT/<sample_id>/<skill>).
Clean originals come from SkillsBench (task A's environment/skills/<skill>, else task B's).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterator

import common as C

STAGE2_ROOT = os.environ.get("SMP_STAGE2_ROOT", "")


def _clean_skill(pair: str, skill: str):
    a, b = pair.split("__", 1)
    for t in (a, b):
        td = C.clean_task_dir(t)
        if td and (td / "environment/skills" / skill).is_dir():
            return td / "environment/skills" / skill
    return None


def smp_items() -> Iterator[Dict]:
    for e in C.manifest()["smp"]:
        sdir = C.SKILLHARM_HF / e["path"]
        ad = json.loads((sdir / "attack_design.json").read_text())
        ms = sdir / "modified_skills"
        stage1: Dict[str, Path] = {}
        if (ms / "SKILL.md").is_file():
            # flat layout: modified_skills/ is itself one skill; name it from modified_files
            names = {m.split("/")[0] for m in ad.get("modified_files", []) if "/" in m}
            stage1[sorted(names)[0] if len(names) == 1 else "unknown"] = ms
        else:
            for d in sorted(ms.iterdir()):
                if d.is_dir():
                    stage1[d.name] = d
        clean = {}
        for sk in stage1:
            c = _clean_skill(e["pair"], sk)
            if c is not None:
                clean[sk] = c
        stage2 = {}
        if STAGE2_ROOT:
            r = Path(STAGE2_ROOT) / e["sample_id"]
            if r.is_dir():
                stage2 = {d.name: d for d in r.iterdir() if d.is_dir()}
        yield {"id": e["sample_id"], "uid": e["sample_id"], "pair": e["pair"], "risk_id": e["risk_id"],
               "design_agent_id": e["design_agent_id"], "modified_files": ad.get("modified_files", []),
               "stage1_dirs": stage1, "clean_dirs": clean, "stage2_dirs": stage2}
