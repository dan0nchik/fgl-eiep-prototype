# SkillHarm defense comparison: none vs authors' prompt vs FGL prompt (+ FGL ablations)

Benchmark: SkillHarm (OSU-NLP, arXiv 2606.02540; data osunlp/SkillHarm CC-BY-4.0; code github.com/OSU-NLP-Group/SkillHarm,
run in place on the run box, not copied here). Run box: ithse.ru (shared), isolated Docker task containers per trial.

## Setup
- Victim: Codex CLI (harbor's `codex` agent, latest npm `@openai/codex` installed in each container), model
  **gpt-5.6-luna** through a ChatGPT-subscription login (the OpenAI API key had no credits; the org is not verified for
  the gpt-5 API family). Auth file bind-mounted read-only into each container (`fgl_harbor.py`). Codex model traffic goes
  through the owner's outbound proxy (OpenAI is geo-blocked from the box); the proxy is injected only into the
  `codex exec` call, not into agent setup.
- Harness: harbor **0.25.0** (the authors' defense launcher `harbor_run.py` works unchanged on it: `CliFlag` and
  `exec_as_agent` present, `codex exec ` marker unchanged). Authors' drivers `eval.sh` / `eval_defense.sh` (FPP) and
  `eval_all.sh` / `eval_defense.sh` + `test_attack*.sh` (SMP), lightly patched (`patch_authors.sh`: renamed harbor entry
  point, no global docker prune, SMP job-dir logging).
- Defense channel: identical for every defense condition: the authors' launcher writes the prompt file to
  `$CODEX_HOME/AGENTS.md` in the same shell command as `codex exec`. Prompts: `authors` = their
  `defensive_system_prompt.md` (322 chars); `fgl` = `fgl_defense_prompt.md` (~2.4k chars); ablations = `ablations/*.md`,
  each deleting exactly one block of the FGL prompt (numbering and the Decision section left as is).
- Primary metric: the authors' deterministic ASR (FPP `tests/run_asr_evaluator.py` -> `asr_result.json`;
  SMP: all `test_detection.py` tests pass after Task B). Utility: harbor verifier `reward.txt`.
- Sample (seed 0): FPP 96 = 8 per risk type, round-robin over tasks (46 tasks); **77 valid** (19 excluded, see below).
  Ablations: the 59 FPP samples = all 49 `none` successes + 10 `none` failures (seed 0). SMP: 24 = 2 per risk type
  (11 pairs). Benign control: 15 clean SkillsBench v1.0 tasks (original skills). Ids: `sample_ids.json`,
  `fpp_valid.tsv`, `fpp_ablation.tsv`, `fpp_excluded.json`.
- Trial validity: any trial whose Codex log shows quota / rate-limit / auth / network errors, or where harbor aborted
  before the agent ran, is moved out (`invalidate.py`) and re-run (max 1 retry per phase); it is never counted as
  "attack failed".
- Parallelism: 8 concurrent trials; about 7-10 min per trial (most of it harbor's per-trial agent install + image build).
