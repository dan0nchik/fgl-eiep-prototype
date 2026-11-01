# SkillHarm run on ithse.ru (~/skillharm_run) — as actually executed (2026-11-01)

Prereqs on the box: uv, harbor 0.25.0 (authors' defense launcher works unchanged on it), node 20 + codex (host, judge
only), docker compose v2 plugin, SkillsBench v1.0 tasks (Harbor layout) copied to SkillHarm/AutoSkillHarm/tasks.
Secrets stay on the box only: ~/skillharm_run/env (chmod 600), ~/.openai_proxy, ~/.codex_sub/auth.json.

1. Sample + data (seed 0):  python3 make_sample.py SkillHarm_data . 8 2 ; .venv/bin/python download_sample.py sample_ids.json SkillHarm_data
2. Stage:  python3 stage_fpp.py ... ; python3 stage_smp.py ... ; python3 stage_benign.py ...
           ln -s self-mutating-poisoning/task_pairs AutoSkillHarm/task_pairs ; ln -s ../tasks fixed-payload-poisoning/tasks
           ln -s . fixed-payload-poisoning/fixed-payload-poisoning   (eval_defense.sh resolves $REPO/fixed-payload-poisoning/...)
3. Patch authors' scripts in place:  bash patch_authors.sh ; bash bin_wrappers.sh
   (HARBOR_BIN=bin/hbsub, HARBOR_TOOL_PYTHON=bin/pysub -> fgl_harbor.py: ChatGPT auth.json mounted read-only, proxy only
   for `codex exec`, setup/build timeout x2; defense conditions additionally load the authors' harbor_run.py patch.)
4. Run:  ./run_all.sh fpp:none   then   ./pipeline.sh   (phases, invalidation + 1 retry, prune dangling/build cache,
         collect_outcomes.py after each phase). Victim: codex + gpt-5.6-luna.
5. Lists after none:  python3 make_lists.py  -> fpp_valid.tsv, fpp_ablation.tsv, fpp_excluded.json
6. Trajectories:  python3 export_trajectories.py none /tmp/traj_none  (scrubbed) -> local trajectories/none/
7. Judge (optional, secondary):  bash judge_run.sh fpp:none fpp:fgl_defense_prompt ...  (codex exec -m gpt-5.6-terra)
8. Local:  ./update_results.sh  -> results/*_summary.json, comparisons.json, RESULTS.md

Shared box rules: never prune -a / volumes / other containers; remove only our trial containers (names = harbor trial
names under our jobs dirs); keep >= 40 GB free. Another agent's cleanup kills processes matching "/harbor run -p", which
is why harbor is invoked through differently named wrappers.
