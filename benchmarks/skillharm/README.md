# FGL defense on SkillHarm (OSU-NLP-Group/SkillHarm)

SkillHarm runs a victim agent (Claude Code / Codex / Gemini CLI / OpenCode) inside a Harbor container
against a poisoned skill, and scores attack success deterministically. The authors expose a single
defense surface: a system prompt injected into the victim via `victim_eval/eval/harbor_run.py`
(selected by `SKILLHARM_DEFENSE_PROMPT_FILE`). We plug FGL in through that same surface, so the FGL
guard is directly comparable to the authors' own defense baseline (`defensive_system_prompt.md`).

- `fgl_defense_prompt.md` — the FGL runtime grounding guard, as a defense system prompt. It encodes the
  FGL action monitor (⑤) at the reasoning level: trust domains, a per-action task-fit / provenance /
  scope / irreversibility check, and a decision rule, expressed so an opaque CLI victim can apply it.
- This is the reasoning-level FGL. The stronger in-loop variant (an execution proxy inside the container
  that intercepts each command and calls the FGL monitor before it runs) is future work: it needs
  container-side tool interception that Harbor does not expose, and the victim CLIs are closed.

## Conditions to compare (all on the AUTHORS' published samples, in isolated containers)
1. `none` — baseline, no defense (run `harbor` directly).
2. `authors_defense` — the authors' `defensive_system_prompt.md`.
3. `fgl` — our `fgl_defense_prompt.md`.

ASR (primary, deterministic, no LLM), cASR and ARR (authors' GPT judge) are reported for each.

## Prerequisites (run box, NOT needed to read this repo)
- Docker with 50+ GB free, Harbor >= 0.6 (`uv tool install harbor`), Python 3.12+.
- `OPENAI_API_KEY` for the Codex victim and the judge (we have no Anthropic/Google keys, so victim = Codex;
  the authors report Claude Code / Gemini / OpenCode too, cited from their paper as reference columns).
- The released benchmark: `huggingface_hub.snapshot_download(repo_id="osunlp/SkillHarm", repo_type="dataset")`
  and the SkillsBench benign task substrate, staged as the scenario READMEs describe.

## Run (FPP, Codex victim)
```bash
cd SkillHarm/AutoSkillHarm
export OPENAI_API_KEY=...            # Codex backend + judge
# 1) baseline
bash fixed-payload-poisoning/victim_eval/scripts/eval_command_codex.sh
# 2) authors' defense
export SKILLHARM_DEFENSE_PROMPT_FILE=fixed-payload-poisoning/victim_eval/eval/defenses/defensive_system_prompt.md
bash fixed-payload-poisoning/victim_eval/scripts/eval_command_codex_defense.sh
# 3) FGL defense — same script, our prompt file
export SKILLHARM_DEFENSE_PROMPT_FILE=/ABS/PATH/fgl-eiep-prototype/benchmarks/skillharm/fgl_defense_prompt.md
bash fixed-payload-poisoning/victim_eval/scripts/eval_command_codex_defense.sh
# metrics (ASR deterministic; cASR/ARR via judge)
bash fixed-payload-poisoning/victim_eval/scripts/compute_metrics.sh
```
SMP (cross-session A→B) is the same pattern under `self-mutating-poisoning/victim_eval/scripts/`
(`test_attack_defense.sh` / `eval_defense.sh` / `compute_metrics.sh`), with the same three prompt files.

## Scope note
We run the authors' published attack samples unchanged, in isolated containers, to measure a defense. We
do NOT run the AutoSkillHarm construction pipeline (it generates new working attacks); that is out of
scope for this evaluation. SkillHarm's code carries no license file — we run it in place and copy nothing
into this repo except our own `fgl_defense_prompt.md`.
