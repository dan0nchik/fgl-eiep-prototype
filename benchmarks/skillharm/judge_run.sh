#!/bin/bash
# usage: judge_run.sh fpp:none fpp:fgl_defense_prompt smp:none ...   (runs on the box; host codex via nvm node 20)
export NVM_DIR=$HOME/.nvm; . $NVM_DIR/nvm.sh; nvm use 20 >/dev/null
cd ~/skillharm_run
for x in "$@"; do python3 judge_codex.py ${x%%:*} ${x#*:} --parallel 2; done
