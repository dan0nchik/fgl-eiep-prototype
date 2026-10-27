# SkillHarm FGL run — remaining steps (server ithse.ru, ~/skillharm_run)

Everything installed: uv, harbor 0.25, node20, Codex CLI 0.165, FGL prompt at ~/fgl_defense_prompt.md,
SkillHarm + skillsbench code cloned. Scripts: ~/skillharm_run/{stage.sh,run_fpp.sh,env.template}.

1. Key + model:
     cd ~/skillharm_run && cp env.template env && nano env    # paste OPENAI_API_KEY, set SKILLHARM_MODEL

2. Authorize Codex once (interactive):
     nvm use 20 && codex login        # or: export OPENAI_API_KEY=... (codex reads it)

3. Download dataset + stage samples (public CC-BY-4.0 attack benchmark):
     bash stage.sh                    # ~10 min, downloads osunlp/SkillHarm, builds the eval tree

4. Smoke one sample first (first harbor run pulls Docker images, several GB):
     NL_TASKS=court-form-filling NL_HARNESS_PARALLEL=1 bash run_fpp.sh none

5. Full three conditions, then metrics:
     bash run_fpp.sh none
     bash run_fpp.sh authors
     bash run_fpp.sh fgl
     bash run_fpp.sh metrics

ASR (deterministic) lands under .../fixed-payload-poisoning/results/<task>/.../evals/<victim>/.
cASR & ARR come from the judge in compute_metrics.sh.

CAVEATS to check on the smoke run:
- harbor here is 0.25; the authors' defense launcher (harbor_run.py) was written for harbor >= 0.6.
  If eval_defense.sh errors on the patch, pin harbor:  uv tool install 'harbor==0.6.3'  and retry.
- Model: if your key can't reach gpt-5.4, set SKILLHARM_MODEL to one it can (e.g. gpt-5.1).
- If eval.sh finds no samples, check NL_RESULTS_DIR=results points at the staged tree.
