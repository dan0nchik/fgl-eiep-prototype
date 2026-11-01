#!/bin/bash
# Victim-eval one condition on the gpt-4.1-mini-generated samples.
# Usage: eval_cond.sh {none|authors|fgl}   [extra NL_* via env]
# Uses harbor 0.6.3 (venv) for ALL conditions so the 3 are comparable.
set -u
source ~/autoskillharm_run/env
export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; nvm use 20 >/dev/null 2>&1 || true
H063=~/autoskillharm_run/harbor063
export PATH="$H063/bin:$HOME/.local/bin:$PATH"       # harbor -> 0.6.3
export HARBOR_TOOL_PYTHON="$H063/bin/python"
export NL_RESULTS_DIR=results
export NL_GENERATOR=codex_gpt-4.1
export NL_HARNESS_MAX_RETRIES=1
export NL_HARNESS_PARALLEL="${NL_HARNESS_PARALLEL:-6}"
MODEL="${SKILLHARM_MODEL:-gpt-4.1-mini}"
V=~/autoskillharm_run/SkillHarm/AutoSkillHarm/fixed-payload-poisoning/victim_eval
case "$1" in
  none)    unset SKILLHARM_DEFENSE_PROMPT_FILE; bash "$V/scripts/eval.sh" codex "$MODEL" ;;
  authors) export SKILLHARM_DEFENSE_PROMPT_FILE="$V/eval/defenses/defensive_system_prompt.md"; bash "$V/scripts/eval_defense.sh" codex "$MODEL" ;;
  fgl)     export SKILLHARM_DEFENSE_PROMPT_FILE=~/fgl_defense_prompt.md;                        bash "$V/scripts/eval_defense.sh" codex "$MODEL" ;;
  *) echo "usage: eval_cond.sh {none|authors|fgl}"; exit 1;;
esac
