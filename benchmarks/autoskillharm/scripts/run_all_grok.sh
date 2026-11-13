#!/bin/bash
# Full AutoSkillHarm grok cycle: usage snapshot -> generate 12 FPP combos -> eval none/authors/fgl.
# Precondition: routerai balance topped up (check: curl /api/v1/key). Re-runnable: combos with
# manifest.json are skipped, eval skips samples with existing asr_result.json.
set -u
cd ~/autoskillharm_run
KEY="$OPENAI_API_KEY"; source ./env; KEY="$OPENAI_API_KEY"
usage(){ curl -s -m 10 "https://routerai.ru/api/v1/key" -H "Authorization: Bearer $KEY" | python3 -c "import sys,json; print(round(json.load(sys.stdin)['data']['usage'],2))" 2>/dev/null; }
mkdir -p genlogs
echo "USAGE_BEFORE: $(usage) RUB  $(date)" | tee -a genlogs/run_all_grok.log
echo "=== STAGE 1: generation (12 combos, parallel 6) ===" | tee -a genlogs/run_all_grok.log
GEN_PARALLEL=6 bash gen_batch.sh >> genlogs/gen_grok_batch.log 2>&1
echo "gen exit: $? ; USAGE_NOW: $(usage) RUB" | tee -a genlogs/run_all_grok.log
echo "=== STAGE 2: victim eval none/authors/fgl ===" | tee -a genlogs/run_all_grok.log
bash eval_all.sh >> genlogs/eval_grok_all.log 2>&1
echo "eval exit: $? ; USAGE_AFTER: $(usage) RUB  $(date)" | tee -a genlogs/run_all_grok.log
echo "RUN_ALL_GROK_DONE" | tee -a genlogs/run_all_grok.log
