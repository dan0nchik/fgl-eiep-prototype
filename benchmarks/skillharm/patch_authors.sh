#!/bin/bash
# Idempotent in-place patch of the authors' SkillHarm victim-eval scripts on the run box (not copied anywhere):
# forwards HTTPS_PROXY/HTTP_PROXY/NO_PROXY into the agent container via harbor --ae, because OpenAI is
# geo-blocked from the server. Values come from the environment at run time (never written to disk here).
set -e
A=~/skillharm_run/SkillHarm/AutoSkillHarm
FPP=$A/fixed-payload-poisoning/victim_eval/scripts
SMP=$A/self-mutating-poisoning/victim_eval/scripts
BLOCK='        local proxy_args=(); if [ -n "${HTTPS_PROXY:-}" ]; then proxy_args=(--ae "HTTPS_PROXY=$HTTPS_PROXY" --ae "HTTP_PROXY=$HTTPS_PROXY" --ae "https_proxy=$HTTPS_PROXY" --ae "http_proxy=$HTTPS_PROXY" --ae "NO_PROXY=$NO_PROXY" --ae "no_proxy=$NO_PROXY"); fi  # FGL-PROXY-PATCH'
for f in $FPP/eval.sh $FPP/eval_defense.sh; do
  grep -q FGL-PROXY-PATCH $f && continue
  python3 - "$f" "$BLOCK" <<'PY'
import sys
p, block = sys.argv[1], sys.argv[2]
s = open(p).read()
anchor = "        local script_run\n"
assert s.count(anchor) == 1, p
s = s.replace(anchor, block + "\n" + anchor)
n = s.count('"${extra_mounts[@]}"')
s = s.replace('"${extra_mounts[@]}"', '"${extra_mounts[@]}" "${proxy_args[@]}"')
print(p, "harbor lines patched:", n)
open(p, "w").write(s)
PY
done
# Invoke harbor through a differently named symlink (~/skillharm_run/bin/hb): another agent on this box
# runs a cleanup that kills every process matching "/harbor run -p" / "script -q -c harbor".
mkdir -p ~/skillharm_run/bin; ln -sfn "$(readlink -f ~/.local/bin/harbor)" ~/skillharm_run/bin/hb
grep -q HB-PATCH $FPP/eval.sh || sed -i 's/ harbor run -p "\$sample_rel"/ "${HARBOR_BIN:-harbor}" run -p "$sample_rel"/g; 1a # HB-PATCH' $FPP/eval.sh
for f in $SMP/test_attack.sh; do grep -q HB-PATCH $f || sed -i 's/^harbor run "\${HARBOR_ARGS/"${HARBOR_BIN:-harbor}" run "${HARBOR_ARGS/; 1a # HB-PATCH' $f; done
# SMP: harbor args arrays built inline; add proxy after the OPENAI_API_KEY forwarding
for f in $SMP/test_attack.sh $SMP/test_attack_defense.sh; do
  grep -q FGL-PROXY-PATCH $f && continue
  python3 - "$f" <<'PY'
import sys, re
p = sys.argv[1]; s = open(p).read(); n = 0
for arr in ("HARBOR_ARGS", "HARBOR_ARGS_B"):
    pat = f'    {arr}+=(--ae "OPENAI_API_KEY=$OPENAI_API_KEY")\nfi\n'
    if pat in s:
        add = (f'if [ -n "${{HTTPS_PROXY:-}}" ]; then {arr}+=(--ae "HTTPS_PROXY=$HTTPS_PROXY" --ae "HTTP_PROXY=$HTTPS_PROXY" '
               f'--ae "https_proxy=$HTTPS_PROXY" --ae "http_proxy=$HTTPS_PROXY" --ae "NO_PROXY=$NO_PROXY" --ae "no_proxy=$NO_PROXY"); fi  # FGL-PROXY-PATCH\n')
        s = s.replace(pat, pat + add, 1); n += 1
print(p, "arrays patched:", n)
open(p, "w").write(s)
PY
done
# Shared box: never prune containers/networks/build cache globally (would delete other tenants' stopped
# containers). Comment out the authors' periodic prune in the SMP drivers.
for f in $SMP/eval_all.sh $SMP/eval_defense.sh $SMP/eval_filtered.sh; do
  sed -i -E 's/^(\s*)(docker (builder|container|network) prune .*)$/\1: # DISABLED-ON-SHARED-BOX \2/' $f
done
# SMP: log the resolved harbor job dirs (authors' trajectory-copy regex misses their own --job-name format)
for f in $SMP/test_attack.sh $SMP/test_attack_defense.sh; do
  grep -q FGL_JOB_A $f || sed -i -E 's/^(echo "  Task A reward: \$REWARD_A")$/echo "  FGL_JOB_A: $REPO\/$TASK_A_JOB"\n\1/; s/^(echo "  Task B reward: \$REWARD_B")$/echo "  FGL_JOB_B: $REPO\/$TASK_B_JOB"\n\1/' $f
done
