#!/usr/bin/env bash
# Incremental offline replay while the online `none` run is still going: every PERIOD seconds export the finished
# trials from the run box with the run's own exporter (export_trajectories.py, secrets scrubbed) into a local
# scratch dir OUTSIDE the repo, then replay all monitors (replay.py resumes; only new trajectories cost calls).
# The final numbers are recomputed on benchmarks/skillharm/trajectories/none/ once it exists (verify_same.py).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOCAL="${LOCAL_TRAJ:-$HOME/dev/bench/skh_traj_partial/none}"
RES="${RES_DIR:-$HOME/dev/bench/skh_replay_partial}"
PERIOD="${PERIOD:-1200}"
ROUNDS="${ROUNDS:-30}"
HPY="$HOME/dev/guardrails-mvp-os/.venv/bin/python"
NPY="$HOME/dev/venvs/nemo/bin/python"
source "$HERE/../../tools/shim.env"
mkdir -p "$LOCAL" "$RES"
for r in $(seq 1 "$ROUNDS"); do
  date
  timeout 300 ssh -o BatchMode=yes ithse.ru 'rm -rf /tmp/skh_export_mine && python3 ~/skillharm_run/export_trajectories.py none /tmp/skh_export_mine' \
    && rsync -a --delete -e "ssh -o BatchMode=yes" ithse.ru:/tmp/skh_export_mine/ "$LOCAL/"
  echo "local trajectories: $(ls "$LOCAL" | wc -l)"
  cd "$HERE"
  "$HPY" replay.py --monitor hermes_builtin --traj "$LOCAL" --out "$RES/hermes_builtin.jsonl" --workers 4 2>&1 | grep -E "trajectories|Traceback"
  "$HPY" replay.py --monitor hermes_smart --traj "$LOCAL" --out "$RES/hermes_smart.jsonl" --workers 8 2>&1 | grep -E "trajectories|Traceback"
  "$HPY" replay.py --monitor fgl --traj "$LOCAL" --out "$RES/fgl.jsonl" --workers 8 2>&1 | grep -E "trajectories|Traceback"
  "$NPY" replay.py --monitor nemo --nemo-variant selfcheck --traj "$LOCAL" --out "$RES/nemo_selfcheck.jsonl" --workers 8 2>&1 | grep -E "trajectories|Traceback"
  "$HPY" locate_harm.py --traj "$LOCAL" --out "$RES/harm_steps.json" --all 2>&1 | tail -1
  "$HPY" score.py --results "$RES" --harm "$RES/harm_steps.json" 2>&1 | cut -c1-220
  [ -d "$HERE/../trajectories/none" ] && [ -n "$(ls -A "$HERE/../trajectories/none" 2>/dev/null)" ] && echo "OFFICIAL_TRAJ_PRESENT"
  [ -f "$HERE/../trajectories/none/DONE" ] && { echo "OFFICIAL_DONE"; break; }
  sleep "$PERIOD"
done
