#!/usr/bin/env python3
"""Lay SMP samples out as the authors' victim_eval/scripts/test_attack*.sh expect:
  self-mutating-poisoning/task_pairs/<pair>/{task_a,task_b,shared_skills,pair_meta.json}   (copied; scripts mutate in place)
  self-mutating-poisoning/task_pairs/<pair>/<risk>/risk_meta.json
  self-mutating-poisoning/task_pairs/<pair>/<risk>/outputs/<designer> -> dataset dir (read-only use)
usage: stage_smp.py DATA_DIR SAMPLE_IDS_JSON PAIRS_DIR"""
import json, os, shutil, sys
data, sample_json, pairs_dir = sys.argv[1:4]
picked = json.load(open(sample_json))["smp"]
n = 0
for r in picked:
    pair, risk = r["pair"], r["risk_id"]
    src_pair = os.path.join(data, "self-mutating-poisoning", "samples", pair)
    dst_pair = os.path.join(pairs_dir, pair)
    if not os.path.isdir(os.path.join(dst_pair, "task_a")):
        os.makedirs(dst_pair, exist_ok=True)
        for x in ("task_a", "task_b", "shared_skills"):
            shutil.copytree(os.path.join(src_pair, x), os.path.join(dst_pair, x), symlinks=True)
        if os.path.isfile(os.path.join(src_pair, "pair_meta.json")):
            shutil.copy(os.path.join(src_pair, "pair_meta.json"), dst_pair)
    rd = os.path.join(dst_pair, risk); os.makedirs(os.path.join(rd, "outputs"), exist_ok=True)
    rm = os.path.join(src_pair, risk, "risk_meta.json")
    if os.path.isfile(rm): shutil.copy(rm, rd)
    link = os.path.join(rd, "outputs", r["design_agent_id"])
    if os.path.islink(link): os.unlink(link)
    os.symlink(os.path.abspath(os.path.join(data, r["path"])), link); n += 1
# The released pair copies declare [environment.env] OPENAI_API_KEY/AZURE_OPENAI_* = "${...}" (the authors' own
# design-time env); harbor refuses to start a trial when any of them is unset ("Missing Environment Variables"),
# and we must not inject an API key (Codex uses the ChatGPT login). The canonical SkillsBench v1.0 task.toml files
# have no such block and no test uses these vars, so drop them from the staged copies.
import re
ENV_LINE = re.compile(r'^\s*(OPENAI_API_KEY|AZURE_OPENAI_[A-Z_]+)\s*=\s*"\$\{[A-Z_]+\}"\s*$')
stripped = 0
for pair in {r["pair"] for r in picked}:
    for role in ("task_a", "task_b"):
        tp = os.path.join(pairs_dir, pair, role, "task.toml")
        if not os.path.isfile(tp): continue
        lines = open(tp).read().splitlines(keepends=True)
        keep = [l for l in lines if not ENV_LINE.match(l)]
        if len(keep) != len(lines):
            open(tp, "w").writelines(keep); stripped += 1
print(f"stripped API-key env passthrough from {stripped} task.toml files")
print(f"staged {n} SMP samples in {len({r['pair'] for r in picked})} pairs")
