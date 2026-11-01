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
- The auth token is valid until 2026-11-05; runs must end before 2026-11-03 ~20:35 UTC (Codex refresh threshold).

## Files
`results/{condition}_summary.json`, `results/comparisons.json`, `results/outcomes.json` (per-trial flags),
`trajectories/none/` (+ README) for offline monitor replay. Scripts: `make_sample.py`, `stage_*.py`,
`patch_authors.sh`, `fgl_harbor.py`, `bin_wrappers.sh`, `run_all.sh`, `pipeline.sh`, `invalidate.py`,
`collect_outcomes.py`, `analyze.py`, `export_trajectories.py`, `judge_codex.py`, `make_results_md.py`.
