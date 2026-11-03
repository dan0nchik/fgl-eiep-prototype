#!/bin/bash
# Orchestrates all SkillHarm phases on the run box. Each phase = authors' driver on our sample, then
# invalidate.py moves infra/API-failed trials out and the phase is re-run (resume) until clean.
# A watchdog kills the phase on subscription rate/usage-limit messages and backs off.
# usage: run_all.sh PHASE [PHASE...]   PHASE = fpp:none | fpp:<slug> | benign:none | benign:<slug> | smp:none | smp:<slug>
source ~/skillharm_run/env
unset OPENAI_API_KEY OPENAI_BASE_URL          # Codex uses the ChatGPT login (fgl_harbor.py), never an API key
export PATH="$HOME/.local/bin:$PATH"
R=~/skillharm_run; A=$R/SkillHarm/AutoSkillHarm
P="${PAR:-8}"; MODEL="$SKILLHARM_MODEL"
LOG=$R/logs; mkdir -p $LOG
prompt_file() {  # slug -> prompt path (basename = slug = authors' evals_defense/<slug>/ dir)
  case "$1" in
    defensive_system_prompt) echo $A/fixed-payload-poisoning/victim_eval/eval/defenses/defensive_system_prompt.md ;;
    *) echo $R/prompts/$1.md ;;
  esac; }
run_phase() {  # scn cond
  local scn=$1 cond=$2
  case $scn in
    fpp|benign)
      cd $A/fixed-payload-poisoning
      export NL_HARNESS_PARALLEL=$P NL_HARNESS_MAX_RETRIES=2
      if [ $scn = fpp ]; then export NL_RESULTS_DIR=results NL_SAMPLE_LIST=${FPP_LIST:-$R/fpp_valid.tsv}; else export NL_RESULTS_DIR=benign; unset NL_SAMPLE_LIST; fi
      if [ $cond = none ]; then bash victim_eval/scripts/eval.sh codex "$MODEL"
      else SKILLHARM_DEFENSE_PROMPT_FILE=$(prompt_file $cond) bash victim_eval/scripts/eval_defense.sh codex "$MODEL"; fi ;;
    smp)
      cd $A
      if [ $cond = none ]; then bash self-mutating-poisoning/victim_eval/scripts/eval_all.sh codex "openai/$MODEL" --parallel $P
      else SKILLHARM_DEFENSE_PROMPT_FILE=$(prompt_file $cond) bash self-mutating-poisoning/victim_eval/scripts/eval_defense.sh codex "openai/$MODEL" --parallel $P --all; fi ;;  # --all: same designs as none (no filter_result.json staged)
  esac; }
my_trial_names() {  # lowercase harbor trial names created by our runs (compose project names)
  find $A/fixed-payload-poisoning/victim_eval/jobs $A/jobs -mindepth 2 -maxdepth 4 -type d -name "*__*" -newer $R/fgl_harbor.py 2>/dev/null \
    | xargs -n1 basename 2>/dev/null | tr 'A-Z' 'a-z' | sort -u; }
cleanup_containers() {  # remove only containers/images of OUR trials that are no longer driven by harbor
  [ -n "${NO_CLEANUP:-}" ] && return   # set when two phases run concurrently (would hit the other phase's live trials)
  local names; names=$(my_trial_names)
  for c in $(docker ps -a --format '{{.Names}}'); do
    local proj=${c%__env-main-1}; [ "$proj" = "$c" ] && proj=${c%-main-1}
    if echo "$names" | grep -qx "$proj"; then
      docker rm -f "$c" >/dev/null 2>&1; docker rmi "${proj}__env-main" >/dev/null 2>&1; docker network rm "${proj}_default" >/dev/null 2>&1
      echo "  cleaned $proj"
    fi
  done; }
ratelimited_recently() {
  find $A/fixed-payload-poisoning/victim_eval/jobs $A/jobs -name codex.txt -mmin -3 2>/dev/null \
    | xargs -r grep -l -i -E '"type":"(error|turn.failed)".*(usage limit|rate limit|too many requests|429)' 2>/dev/null | head -1; }
for ph in "$@"; do
  scn=${ph%%:*}; cond=${ph#*:}; backoff=900
  for attempt in 1 2; do   # at most 1 retry per phase
    echo "$(date -Iseconds) PHASE $ph attempt $attempt (P=$P)" | tee -a $LOG/run_all.log
    setsid bash -c "$(declare -f run_phase prompt_file); A=$A R=$R P=$P MODEL=$MODEL FPP_LIST=${FPP_LIST:-}; run_phase $scn $cond" >> $LOG/phase_${scn}_${cond}.log 2>&1 &
    pid=$!; limited=0
    while kill -0 $pid 2>/dev/null; do
      sleep 60
      f=$(ratelimited_recently)
      if [ -n "$f" ]; then
        echo "$(date -Iseconds) RATE LIMIT seen ($f) -> killing phase, backoff ${backoff}s" | tee -a $LOG/run_all.log
        kill -TERM -$pid 2>/dev/null; sleep 10; kill -KILL -$pid 2>/dev/null; limited=1; break
      fi
    done
    wait $pid 2>/dev/null
    cleanup_containers >> $LOG/run_all.log 2>&1
    inv=$(python3 $R/invalidate.py $scn $cond --apply); echo "$(date -Iseconds) $inv" | tee -a $LOG/run_all.log
    n=$(echo "$inv" | python3 -c "import sys,json;print(json.load(sys.stdin)['invalid'])")
    if [ $limited = 1 ]; then sleep $backoff; backoff=$((backoff*2)); continue; fi
    [ "$n" = "0" ] && break
  done
  echo "$(date -Iseconds) PHASE $ph DONE" | tee -a $LOG/run_all.log
  # shared box: reclaim dangling images + build cache only (never -a, never volumes)
  docker image prune -f >/dev/null 2>&1; docker builder prune -f >/dev/null 2>&1
  echo "$(date -Iseconds) disk free: $(df -h / | tail -1 | awk '{print $4}')" | tee -a $LOG/run_all.log
  python3 $R/collect_outcomes.py $R/outcomes.json >> $LOG/run_all.log 2>&1
  touch $R/DONE_${scn}_${cond}
done
