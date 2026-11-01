"""Carry over replay records computed incrementally on early exports of the SAME online run, but only for
trajectories that are provably identical to the official export: same id, same number of normalized steps, and the
same ordered sequence of (step index, sha256 of every vetted action string). Everything else is replayed again.

usage: python reuse_partial.py --partial ~/dev/bench/skh_replay_partial --official-traj ../trajectories/none \
                               --out results
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import replay  # noqa: E402
import traj_io  # noqa: E402


def signature(t):
    sig = []
    for s in t["steps"]:
        a = replay.action_of(s)
        if a is not None:
            sig.append((s["i"], replay.h(a[1])))
    return len(t["steps"]), sig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--partial", required=True)
    ap.add_argument("--official-traj", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    off = {t["sample_id"]: signature(t) for t in traj_io.load_dir(Path(a.official_traj))}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    reused_ids = set()
    for f in sorted(Path(a.partial).glob("*.jsonl")):
        dst = out / f.name
        have = set()
        if dst.exists():
            have = {json.loads(l)["sample_id"] for l in dst.read_text().splitlines() if l.strip()}
        n = 0
        with dst.open("a") as w:
            for line in f.read_text().splitlines():
                r = json.loads(line)
                sid = r["sample_id"]
                if sid in have or sid not in off:
                    continue
                nsteps, sig = off[sid]
                rsig = [(d["i"], d["cmd_h"]) for d in r["decisions"]]
                if r["n_steps"] == nsteps and rsig == sig:
                    w.write(line + "\n")
                    n += 1
                    reused_ids.add(sid)
        print(f"{f.name}: reused {n}")
    hp = Path(a.partial) / "harm_steps.json"
    if hp.exists():
        harm = json.loads(hp.read_text())
        dst = out / "harm_steps.json"
        cur = json.loads(dst.read_text()) if dst.exists() else {}
        for sid in reused_ids:
            if sid in harm and sid not in cur:
                cur[sid] = harm[sid]
        dst.write_text(json.dumps(cur, indent=1))
        print("harm steps carried:", len(cur))


if __name__ == "__main__":
    main()
