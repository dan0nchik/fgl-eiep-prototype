## Deviations from the paper protocol / caveats
- Victim model gpt-5.6-luna (subscription), not the paper's gpt-5.4 (API). Single victim (Codex only).
- Subset, not the full benchmark: FPP 77/687, SMP 24/192. Ablations only on the 59-sample FPP subset described above.
- 19 of 96 sampled FPP attacks excluded: harbor's Codex agent setup (`nvm install 22`) fails deterministically in those
  task images ("Version '22' not found"; 11 tasks, incl. travel-planning 5, seismic-phase-picking 3,
  software-dependency-audit 3). Excluded from every condition, so comparisons are paired.
- SkillsBench substrate: v1.0 Harbor layout (the current v1.1 layout is incompatible with the authors' drivers). For two
  SMP tasks the canonical `tests/test.sh` used by the authors' restore step was aligned to the released pair copy.
- FPP `attacker_goal.json` is not in the public release; for cASR/ARR the judge receives the risk type's objective from
  `risk_taxonomy.json` instead (SMP uses the released `risk_behavior`). Judge = gpt-5.6-terra via `codex exec`
  (`judge_codex.py`), not the authors' gpt-5.5/gpt-5.4 API judge. Judge metrics are secondary; ASR is primary.
- The FGL prompt is ~7x longer than the authors' prompt; the comparison is prompt vs prompt through the same channel,
  not an in-loop FGL monitor.
- Codex runs with `--dangerously-bypass-approvals-and-sandbox` (harbor default for this agent, as in the paper).
- The auth token is valid until 2026-11-05; runs had to end before 2026-11-03 ~20:35 UTC (Codex refresh threshold). All
  runs finished 22:05 MSK; the subscription login (~/.codex_sub) was deleted from the run box at 22:40 MSK
  (no auth.json copies existed under ~/skillharm_run).

## SMP (self-mutating poisoning) notes
- First SMP attempt (2026-11-02) produced no data: all 48 trials (24 none + 24 fgl) stopped before Task A with harbor's
  "Missing Environment Variables" (OPENAI_API_KEY, AZURE_OPENAI_API_KEY/ENDPOINT/API_VERSION). Root cause: the released
  SMP pair copies (`task_pairs/<pair>/task_{a,b}/task.toml`) declare `[environment.env] X = "${X}"` for these four vars
  (the authors' own design-time env); harbor refuses to start a trial when any is unset, and `run_all.sh` deliberately
  unsets OPENAI_API_KEY (Codex uses the ChatGPT login). The `codex_gpt-5.4` in the trial path is the attack *designer*
  id, not the victim (runner id was correctly `codex_gpt-5.6-luna`). Fix (`stage_smp.py`): drop those four lines from
  the 22 staged task.toml files; the canonical SkillsBench v1.0 task.toml files have no such block and no test uses
  these vars. No dummy key was injected.
- Second blocker for the defense condition: the authors' SMP `eval_defense.sh` by default runs only designs with a
  `filter/<designer>/filter_result.json` verdict `keep`, which the public release does not ship, so it ran 0 designs.
  `run_all.sh` now passes `--all`, so the fgl condition runs exactly the same 24 designs as none (paired n = 24).
- Re-runs after infra errors (proxy/stream errors in codex.txt, `invalidate.py`): none 5 trials, fgl 6 + 2 trials;
  final: none 24/24 valid, fgl 24/24 valid.
- SMP task success under attack (harbor reward = 1): none Task A 13/24, Task B 11/24 (both 8/24); fgl Task A 6/24,
  Task B 8/24 (both 2/24). The FGL prompt lowers SMP ASR from 14/24 to 11/24 (discordant 4 vs 1, McNemar p = 0.375,
  not significant at n = 24) while roughly halving Task A success, so part of the ASR reduction may come from the agent
  doing less work in Task A rather than from rejecting the mutation.
- One none trial ran Task B but produced no detection results (0 passed / 0 failed); per the authors' parser it counts
  as attack not successful.
- Defense injection verified on a fgl SMP trial (FGL prompt marker present in the Task A agent files, absent in a none
  trial).

## Files
`results/{condition}_summary.json`, `results/comparisons.json`, `results/outcomes.json` (per-trial flags),
`trajectories/none/` (+ README) for offline monitor replay. Scripts: `make_sample.py`, `stage_*.py`,
`patch_authors.sh`, `fgl_harbor.py`, `bin_wrappers.sh`, `run_all.sh`, `pipeline.sh`, `invalidate.py`,
`collect_outcomes.py`, `analyze.py`, `export_trajectories.py`, `judge_codex.py`, `make_results_md.py`.
