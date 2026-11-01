#!/bin/bash
# Run victim_eval for all 3 conditions sequentially (container cap friendly).
# Optional: NL_REALIZATIONS to subset (e.g. plain_text). NL_HARNESS_PARALLEL default 6.
set -u
LOGD=~/autoskillharm_run/genlogs; mkdir -p "$LOGD"
for cond in none authors fgl; do
  echo "===== EVAL $cond  $(date +%T) ====="
  bash ~/autoskillharm_run/eval_cond.sh "$cond" > "$LOGD/eval_${cond}.log" 2>&1
  echo "EVAL_${cond}_DONE_$?"
done
echo "EVAL_ALL_DONE"
