#!/usr/bin/env python3
"""Lay the sampled FPP samples out in the tree the authors' victim_eval/eval.sh walks:
  results/<task>/<slug>/<risk>/outputs/<generator>/{manifest.json, samples/<sample_id> -> dataset dir}
The released dataset has no per-generator manifest.json (eval.sh requires one), so we build it from
fpp_index.jsonl (sample_id, realization, target_task_relative_path).
usage: stage_fpp.py DATA_DIR SAMPLE_IDS_JSON RESULTS_DIR"""
import ast, json, os, sys
from collections import defaultdict
data, sample_json, results = sys.argv[1:4]
picked = json.load(open(sample_json))["fpp"]
groups = defaultdict(list)
for r in picked:
    groups[(r["task_id"], r["target_slug"], r["risk_id"], r["design_agent_id"])].append(r)
n = 0
for (task, slug, risk, gen), rows in groups.items():
    out = os.path.join(results, task, slug, risk, "outputs", gen)
    os.makedirs(os.path.join(out, "samples"), exist_ok=True)
    def added(r):  # metadata.json stores added_artifacts as a python-literal string
        m = json.load(open(os.path.join(data, r["path"], "metadata.json")))
        a = m.get("added_artifacts") or []
        return ast.literal_eval(a) if isinstance(a, str) else a
    man = [{"sample_id": r["sample_id"], "realization": r["realization"], "added_artifacts": added(r),
            "target_task_relative_path": r["target_path"], "risk_id": r["risk_id"]} for r in rows]
    json.dump(man, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    if os.environ.get("MANIFEST_ONLY"): continue
    for r in rows:
        src = os.path.abspath(os.path.join(data, r["path"]))
        assert os.path.isfile(os.path.join(src, "task.toml")), src
        dst = os.path.join(out, "samples", r["sample_id"])
        if os.path.islink(dst): os.unlink(dst)
        os.symlink(src, dst); n += 1
print(f"staged {n} FPP samples in {len(groups)} groups under {results}")
