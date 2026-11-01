#!/bin/bash
# Generate FPP attacks for every combo in combos.tsv, codex+gpt-5-mini, proxy, parallel cap 6.
set -u
source ~/autoskillharm_run/env
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; nvm use 20 >/dev/null 2>&1 || true
export NL_RESULTS_DIR=results
export NL_HARNESS_MAX_RETRIES=1
MODEL="${SKILLHARM_MODEL:-gpt-5-mini}"
SCRIPTS=~/autoskillharm_run/SkillHarm/AutoSkillHarm/fixed-payload-poisoning/attack_design/scripts
COMBOS=~/autoskillharm_run/combos.tsv
PAR="${GEN_PARALLEL:-6}"
LOGD=~/autoskillharm_run/genlogs; mkdir -p "$LOGD"
PIDS=()
prune(){ local n=(); for p in "${PIDS[@]:-}"; do kill -0 "$p" 2>/dev/null && n+=("$p"); done; PIDS=("${n[@]:-}"); }
i=0
while IFS=$(printf "\t") read -r t r p; do
  [ -z "${t:-}" ] && continue
  case "$t" in \#*) continue;; esac
  i=$((i+1))
  slug=$(echo "$p" | sed "s|/|--|g; s|\.|_|g" | tr "[:upper:]" "[:lower:]")
  L="$LOGD/gen_${t}_${r}.log"
  echo "[launch $i] $t / $r / $slug -> $L"
  ( bash "$SCRIPTS/run_one.sh" "$t" "$r" "$p" codex "$MODEL" > "$L" 2>&1; echo "GEN_DONE_$? $t $r" >> "$L" ) &
  PIDS+=($!)
  while prune; [ "${#PIDS[@]}" -ge "$PAR" ]; do sleep 3; prune; done
done < "$COMBOS"
wait
echo "GEN_BATCH_COMPLETE"
