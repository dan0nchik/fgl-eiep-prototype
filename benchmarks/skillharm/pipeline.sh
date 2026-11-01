#!/bin/bash
# Priority order set by coordinator (2026-11-01): fpp fgl -> fpp authors -> ablations (none-successes + 10 failures)
# -> SMP none+fgl (2 per risk) -> benign none+fgl.
R=~/skillharm_run
FPP_LIST=$R/fpp_valid.tsv    $R/run_all.sh fpp:fgl_defense_prompt fpp:defensive_system_prompt
FPP_LIST=$R/fpp_ablation.tsv $R/run_all.sh fpp:fgl_no_taskfit fpp:fgl_no_provenance fpp:fgl_no_scope fpp:fgl_no_irrev fpp:fgl_no_explicit_list
$R/run_all.sh smp:none smp:fgl_defense_prompt
$R/run_all.sh benign:none benign:fgl_defense_prompt
echo "$(date -Iseconds) PIPELINE DONE" >> $R/logs/run_all.log
