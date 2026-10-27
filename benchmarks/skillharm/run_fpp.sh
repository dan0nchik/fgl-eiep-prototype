#!/bin/bash
# Run SkillHarm FPP victim eval (Codex victim) in three defense conditions, then compute metrics.
# Prereqs: ~/skillharm_run/env filled (OPENAI_API_KEY), stage.sh already run, Codex authed, Docker up.
set -e
source ~/skillharm_run/env
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; nvm use 20 >/dev/null 2>&1
export NL_RESULTS_DIR=results
export NL_HARNESS_PARALLEL="${NL_HARNESS_PARALLEL:-4}"
MODEL="${SKILLHARM_MODEL:-gpt-5.4}"
SCRIPTS=~/skillharm_run/SkillHarm/AutoSkillHarm/fixed-payload-poisoning/victim_eval/scripts
FGL_PROMPT=~/fgl_defense_prompt.md
AUTHORS_PROMPT=~/skillharm_run/SkillHarm/AutoSkillHarm/fixed-payload-poisoning/victim_eval/eval/defenses/defensive_system_prompt.md

case "$1" in
  none)     echo "[none]";     unset SKILLHARM_DEFENSE_PROMPT_FILE; bash "$SCRIPTS/eval.sh" codex "$MODEL" ;;
  authors)  echo "[authors]";  export SKILLHARM_DEFENSE_PROMPT_FILE="$AUTHORS_PROMPT"; NL_VICTIM_SUFFIX=_authors bash "$SCRIPTS/eval_defense.sh" codex "$MODEL" ;;
  fgl)      echo "[fgl]";      export SKILLHARM_DEFENSE_PROMPT_FILE="$FGL_PROMPT";     NL_VICTIM_SUFFIX=_fgl     bash "$SCRIPTS/eval_defense.sh" codex "$MODEL" ;;
  metrics)  bash "$SCRIPTS/compute_metrics.sh" ;;
  *) echo "usage: $0 {none|authors|fgl|metrics}  (run none/authors/fgl, then metrics)"; exit 1 ;;
esac
