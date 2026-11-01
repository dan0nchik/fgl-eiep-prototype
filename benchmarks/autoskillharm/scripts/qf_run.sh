#!/bin/bash
set -u
source ~/autoskillharm_run/env
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; nvm use 20 >/dev/null 2>&1 || true
export STATIC_FILTER_PARALLEL="${STATIC_FILTER_PARALLEL:-6}"
export NL_DESIGNERS=codex_gpt-4.1
QF=~/autoskillharm_run/SkillHarm/AutoSkillHarm/fixed-payload-poisoning/quality_filter
bash "$QF/scripts/run_all_filter.sh" codex gpt-4.1
