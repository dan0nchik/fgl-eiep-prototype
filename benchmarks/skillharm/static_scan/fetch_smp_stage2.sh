#!/usr/bin/env bash
# Fetch SMP stage-2 (post-Task-A, mutated) skill snapshots from the online `none` run on the run box.
# SkillHarm's SMP harness tars the skills folder at the end of Task A into
#   <task A job>/verifier/skills_snapshot.tar.gz   (self-mutating-poisoning/victim_eval/scripts/test_attack.sh)
# and overlays it into Task B. That snapshot is exactly what a Hermes re-scan (`hermes skills audit`) would see.
# Snapshots are stored OUTSIDE the repo: $DEST/<sample_id>/<skill>/...
# Then: SMP_STAGE2_ROOT=$DEST python hermes_static_scan.py
set -euo pipefail
DEST="${DEST:-$HOME/dev/bench/skh_smp_stage2}"
VICTIM="${VICTIM_ID:-codex_gpt-5.6-luna}"
mkdir -p "$DEST"
ssh -o BatchMode=yes ithse.ru "VICTIM=$VICTIM bash -s" <<'EOF' > /tmp/skh_stage2_list.txt
ROOT=~/skillharm_run/SkillHarm/AutoSkillHarm/self-mutating-poisoning/task_pairs
for d in $ROOT/*/*/eval/designer_*/runner_$VICTIM/; do
  [ -f "$d/eval_result.json" ] || continue
  job=$(grep -o "FGL_JOB_A: [^ ]*" "$d/eval.log" | head -1 | awk '{print $2}')
  tarf="$job/verifier/skills_snapshot.tar.gz"
  [ -f "$tarf" ] || continue
  sid=$(python3 -c "import json,sys;r=json.load(open('$d/eval_result.json'));print(r['pair']+'__'+r['risk_type']+'__'+r['design_agent_id'])")
  echo "$sid $tarf"
done
EOF
n=0
while read -r sid tarf; do
  [ -n "$sid" ] || continue
  mkdir -p "$DEST/$sid"
  ssh -o BatchMode=yes ithse.ru "cat '$tarf'" | tar xzf - -C "$DEST/$sid" && n=$((n+1))
done < /tmp/skh_stage2_list.txt
echo "fetched $n stage-2 snapshots into $DEST"
