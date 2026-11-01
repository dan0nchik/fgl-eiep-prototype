#!/bin/bash
# (local) Pull outcomes from the run box, recompute summaries, rebuild RESULTS.md. Safe to run repeatedly.
cd "$(dirname "$0")"
for i in 1 2 3 4; do /tmp/shs 'cd ~/skillharm_run; python3 collect_outcomes.py outcomes.json >/dev/null; tail -40 logs/run_all.log | grep -E "PHASE|disk" | tail -30' > /tmp/sh_phases.txt 2>/dev/null && break; sleep 30; done
for i in 1 2 3 4; do scp -q -o ControlPath=/tmp/shmux-%r@%h:%p -P 1122 hromov@ithse.ru:skillharm_run/outcomes.json results/outcomes.json 2>/dev/null && break; sleep 30; done
[ -f /tmp/risk_taxonomy.json ] || scp -q -o ControlPath=/tmp/shmux-%r@%h:%p -P 1122 hromov@ithse.ru:skillharm_run/SkillHarm/AutoSkillHarm/risk_taxonomy.json /tmp/
python3 analyze.py results/outcomes.json /tmp/risk_taxonomy.json results > /tmp/sh_analyze.txt
python3 make_results_md.py results > /tmp/sh_tables.md
{
cat RESULTS_head.md
echo; echo "## Results (auto-generated $(date '+%Y-%m-%d %H:%M %Z'); partial until all phases finish)"; echo
cat /tmp/sh_tables.md
echo; echo "### Phase log (run box, last entries)"; echo; echo '```'; cat /tmp/sh_phases.txt; echo '```'
echo; cat RESULTS_tail.md
} > RESULTS.md
echo "RESULTS.md rebuilt"; cat /tmp/sh_analyze.txt
