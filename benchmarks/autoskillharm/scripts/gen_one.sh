#!/bin/bash
# Drive the FPP attack_design harness for ONE combo with codex+gpt-5-mini through the proxy.
set -e
source ~/autoskillharm_run/env
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; nvm use 20 >/dev/null 2>&1 || true
export NL_RESULTS_DIR=results
export NL_HARNESS_MAX_RETRIES=1
SCRIPTS=~/autoskillharm_run/SkillHarm/AutoSkillHarm/fixed-payload-poisoning/attack_design/scripts
bash "$SCRIPTS/run_one.sh" "$1" "$2" "$3" codex "${SKILLHARM_MODEL:-gpt-5-mini}"
