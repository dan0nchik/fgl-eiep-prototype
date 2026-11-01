"""Hermes Agent skills_guard (hermes-agent 0.19.0) on SkillHarm poisoned skills vs their clean originals.

Exactly what `hermes skills install <community skill>` does before installing (hermes_cli/skills_hub.py):
    result = scan_skill(quarantine_dir, source=<community identifier>)   # (scan_skill_cached = same + cache)
    allowed, reason = should_allow_install(result)                       # INSTALL_POLICY
We call both functions from the installed package; no Hermes logic is re-implemented here. The verdict does not
depend on `source`; only the install policy does, so we evaluate the policy for every trust level:
    community (any GitHub/skills.sh skill)       safe->allow  caution->block  dangerous->block
    agent-created (only if skills.guard_agent_created=True; default False -> NO scan at all)
                                                 safe->allow  caution->allow  dangerous->ask(=error to agent)
    trusted (openai/skills, anthropics/skills, ...) safe->allow caution->allow dangerous->block

Run with the venv that has hermes-agent:  ~/dev/guardrails-mvp-os/.venv/bin/python hermes_static_scan.py
Output: results/hermes_static_scan.json (ids, verdicts, pattern ids, severities, file names, match hashes only).
"""
from __future__ import annotations

import json
import sys
import tempfile
import os
from pathlib import Path

os.environ.setdefault("HERMES_HOME", tempfile.mkdtemp(prefix="hermes_static_home_"))
sys.path.insert(0, str(Path(__file__).parent))

from tools import skills_guard as SG  # noqa: E402  (Hermes)
import common as C  # noqa: E402
import smp_items  # noqa: E402


def scan(skill_dir: Path) -> dict:
    r = SG.scan_skill(skill_dir, source="community")
    allowed_comm, reason = SG.should_allow_install(r)
    out = {"verdict": r.verdict, "trust_level": r.trust_level,
           "install_community": {True: "allow", False: "block", None: "ask"}[allowed_comm],
           "install_community_reason": reason[:160],
           "findings": [{"pattern_id": f.pattern_id, "severity": f.severity, "category": f.category,
                         "file": f.file, "match_h": C.sha(f"{f.pattern_id}|{f.file}|{f.match}")}
                        for f in r.findings]}
    for src, key in (("agent-created", "install_agent_created"), ("openai/skills", "install_trusted")):
        r2 = SG.scan_skill(skill_dir, source=src)
        assert r2.verdict == r.verdict
        a, _ = SG.should_allow_install(r2)
        out[key] = {True: "allow", False: "block", None: "ask"}[a]
    return out


def main():
    C.OUT_DIR.mkdir(exist_ok=True)
    res = {"scanner": "hermes-agent 0.19.0 tools/skills_guard.py scan_skill + should_allow_install",
           "scanner_version": getattr(SG, "SCANNER_VERSION", None),
           "n_threat_patterns": len(SG.THREAT_PATTERNS), "poisoned": [], "clean": [], "smp_stage2": []}
    clean_seen = {}
    for it in C.fpp_items():
        rec = {k: it[k] for k in ("id", "uid", "scenario", "task_id", "risk_id", "realization", "carrier_point_type",
                                  "skill", "target_rel", "added_rel")}
        rec.update(scan(it["poisoned_dir"]))
        res["poisoned"].append(rec)
        key = (it["task_id"], it["skill"])
        if key not in clean_seen and it["clean_dir"] is not None and it["clean_dir"].is_dir():
            c = {"task_id": it["task_id"], "skill": it["skill"], "scenario": "FPP"}
            c.update(scan(it["clean_dir"]))
            clean_seen[key] = c
            res["clean"].append(c)
        elif key not in clean_seen:
            clean_seen[key] = None
            res["clean"].append({"task_id": it["task_id"], "skill": it["skill"], "scenario": "FPP",
                                 "missing": True})
    for it in smp_items.smp_items():
        for stage, d in it["stage1_dirs"].items():
            rec = {"id": it["id"], "uid": it["uid"], "scenario": "SMP", "pair": it["pair"], "risk_id": it["risk_id"],
                   "design_agent_id": it["design_agent_id"], "skill": stage, "stage": "stage1"}
            rec.update(scan(d))
            res["poisoned"].append(rec)
        for stage, d in it.get("stage2_dirs", {}).items():
            rec = {"id": it["id"], "uid": it["uid"], "scenario": "SMP", "pair": it["pair"],
                   "risk_id": it["risk_id"], "skill": stage, "stage": "stage2"}
            rec.update(scan(d))
            res["smp_stage2"].append(rec)
        for skill, d in it.get("clean_dirs", {}).items():
            key = ("SMP:" + it["pair"], skill)
            if key not in clean_seen:
                c = {"task_id": "SMP:" + it["pair"], "skill": skill, "scenario": "SMP"}
                c.update(scan(d))
                clean_seen[key] = c
                res["clean"].append(c)
    out = C.OUT_DIR / "hermes_static_scan.json"
    out.write_text(json.dumps(res, indent=1))
    print("wrote", out, len(res["poisoned"]), "poisoned recs,", len(res["clean"]), "clean,",
          len(res["smp_stage2"]), "smp stage2")


if __name__ == "__main__":
    main()
