#!/usr/bin/env python3
"""Download only the sampled FPP sample dirs + all SMP samples from osunlp/SkillHarm (CC-BY-4.0)."""
import json, sys
from huggingface_hub import snapshot_download
d = json.load(open(sys.argv[1]))
pats = [r["path"] + "/**" for r in d["fpp"]] + ["self-mutating-poisoning/**", "*.jsonl", "MANIFEST.json"]
snapshot_download(repo_id="osunlp/SkillHarm", repo_type="dataset", local_dir=sys.argv[2], allow_patterns=pats, max_workers=8)
print("done")
