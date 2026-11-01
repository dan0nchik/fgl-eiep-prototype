#!/usr/bin/env python3
"""Benign utility control: N clean SkillsBench v1.0 tasks (original, unpoisoned skills), seed 0, drawn from
the tasks covered by the FPP sample. Laid out like an FPP results tree so the authors' eval.sh /
eval_defense.sh run them with the identical defense-injection path:
  <BENIGN_DIR>/<task>/clean/benign/outputs/original/{manifest.json, samples/benign__<task> -> tasks/<task>}
No ASR evaluator exists for these; utility = harbor verifier reward.txt.
usage: stage_benign.py SAMPLE_IDS_JSON TASKS_DIR BENIGN_DIR [N=15]"""
import json, os, random, sys
sample_json, tasks_dir, out_dir = sys.argv[1:4]
n = int(sys.argv[4]) if len(sys.argv) > 4 else 15
tasks = sorted({r["task_id"] for r in json.load(open(sample_json))["fpp"]})
tasks = [t for t in tasks if os.path.isfile(os.path.join(tasks_dir, t, "task.toml"))]
pick = sorted(random.Random(0).sample(tasks, n))
for t in pick:
    gen = os.path.join(out_dir, t, "clean", "benign", "outputs", "original")
    os.makedirs(os.path.join(gen, "samples"), exist_ok=True)
    sid = f"benign__{t}"
    json.dump([{"sample_id": sid, "realization": "clean", "target_task_relative_path": None}],
              open(os.path.join(gen, "manifest.json"), "w"))
    dst = os.path.join(gen, "samples", sid)
    if os.path.islink(dst): os.unlink(dst)
    os.symlink(os.path.abspath(os.path.join(tasks_dir, t)), dst)
json.dump(pick, open(os.path.join(out_dir, "benign_tasks.json"), "w"), indent=1)
print(f"staged {len(pick)} benign tasks (of {len(tasks)} eligible): {pick}")
