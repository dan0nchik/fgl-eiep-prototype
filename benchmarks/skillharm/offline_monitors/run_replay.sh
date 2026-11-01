#!/usr/bin/env bash
# Offline replay of all monitors over one directory of exported SkillHarm trajectories, then scoring.
# usage: bash run_replay.sh <traj_dir> [results_dir]
# LLM monitors go through the local Codex shim (benchmarks/tools/codex_shim.py on :8765, model gpt-5.6-luna);
# start it first:  python3 benchmarks/tools/codex_shim.py --port 8765 &
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TRAJ="${1:?traj dir}"
RES="${2:-$HERE/results}"
HPY="${HERMES_PY:-$HOME/dev/guardrails-mvp-os/.venv/bin/python}"
NPY="${NEMO_PY:-$HOME/dev/venvs/nemo/bin/python}"
source "$HERE/../../tools/shim.env"
mkdir -p "$RES"
cd "$HERE"
"$HPY" replay.py --monitor hermes_builtin --traj "$TRAJ" --out "$RES/hermes_builtin.jsonl" --workers 4
"$HPY" replay.py --monitor hermes_smart   --traj "$TRAJ" --out "$RES/hermes_smart.jsonl"   --workers 8
"$HPY" replay.py --monitor fgl            --traj "$TRAJ" --out "$RES/fgl.jsonl"            --workers 8
"$NPY" replay.py --monitor nemo --nemo-variant selfcheck --traj "$TRAJ" --out "$RES/nemo_selfcheck.jsonl" --workers 8
"$HPY" locate_harm.py --traj "$TRAJ" --out "$RES/harm_steps.json" --all
"$HPY" score.py --results "$RES" --harm "$RES/harm_steps.json"
