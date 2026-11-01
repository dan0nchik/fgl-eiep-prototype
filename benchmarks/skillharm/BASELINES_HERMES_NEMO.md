# SkillHarm: Hermes Agent built-in skill defenses, NVIDIA NeMo Guardrails and the FGL monitor

Defensive evaluation on the public SkillHarm benchmark (OSU-NLP, arXiv 2606.02540; dataset `osunlp/SkillHarm`,
CC-BY-4.0; 879 attack samples = FPP 687 + SMP 192). Two parts:

* **Part A, install time (static).** Would the defense have refused the poisoned skill before it was ever used?
  Hermes `skills_guard` exactly as `hermes skills install` runs it, and a NeMo input rail used as a skill-vetting
  analog. Poisoned skills vs. the clean originals of the same skills (false positives).
* **Part B, run time (offline replay).** Each monitor is replayed over the recorded actions of the victim
  agent (Codex, `none` condition) from the online SkillHarm run. **Offline replay, no counterfactual
  continuation**: a block is recorded, but the trajectory after it is not re-run.

No attack payloads are stored in this repo: the result files hold sample ids, verdicts, pattern ids, severities,
relative file names and short content hashes only. The dataset lives outside the repo (`~/dev/bench/skillharm_hf`).

## Part A: install-time scans

### Data
* Poisoned skills: for every one of the 879 samples, the poisoned skill directory as shipped in the dataset
  (FPP: `<sample>/environment/skills/<skill>/`, the owning skill of the poisoned file, including any added
  artifact; SMP: `<sample>/modified_skills/<skill>/`, the stage-1 package as installed, 1 to 3 skills per sample).
* Clean originals: the same skills from SkillsBench (`benchflow-ai/skillsbench`, `tasks/` + `tasks-extra/`;
  the three `mario-coin-counting` skills were renamed upstream after SkillHarm was built, so they come from
  skillsbench@4e9eb449, the parent of the renaming commit). 109 clean (task, skill) directories: 94 for FPP
  (71 distinct skill names) + 15 for SMP. Every poisoned sample has its clean original. In 19 FPP samples
  (3 skills) the poisoned directory differs from the current clean original in files other than the declared
  target / added artifacts (secondary edits or upstream drift); the "attack-attributable" column below
  controls for this.
* Unique sample key: FPP `sample_id` is not unique across tasks (a shared skill such as `pdf` yields the same
  id in several tasks), so samples are keyed by `task_id/sample_id`.

### Methods
**Hermes (hermes-agent 0.19.0, `tools/skills_guard.py`, scanner `skills-guard-v1`, 121 threat patterns).**
`scan_skill(dir, source="community")` + `should_allow_install(result)`, imported from the installed package,
i.e. what `hermes skills install` does for any GitHub / skills.sh skill (`hermes_cli/skills_hub.py`). Policy:
community = safe→allow, caution→block, dangerous→block (a verdict is `caution` with any high finding,
`dangerous` with any critical one; medium/low findings do not block). The same scan under
`source="agent-created"` (policy safe/caution→allow, dangerous→ask) is reported too, but that gate runs only if
`skills.guard_agent_created=true`; it is **off by default**, and the SMP mutation is written by an `atexit` hook
in a script (direct file I/O), which never passes through Hermes's skill-manager write path anyway.
"Attack-attributable" = blocked AND the poisoned skill has a high/critical finding (pattern, file, match hash)
that its clean original does not have (size/file-count findings compared by pattern and file only). This removes
blocks that the benign skill would also get.

**NeMo Guardrails 0.24.1 input rail.** NeMo has no skill-install hook; as the closest analog the skill text is
treated as an untrusted user message and the library's input rail is run on it
(`LLMRails.check([{"role":"user","content":chunk}], rail_types=[INPUT])`, via
`benchmarks/agent_safetybench/guards/nemo_guard.py`). Two rail configs: `self check input` (library example
policy, verbatim) and `content safety check input` (NemoGuard/Aegis 23-category prompt). Text is split per file
into 6000-char chunks (300 overlap); a skill is blocked if any chunk is blocked. Scopes: SKILL.md only (as
specified), and, for content-safety, all text files of the skill (payloads often sit in a script or an added doc).
Self-check was not run on all text: it already blocks 98% of clean SKILL.md files.
Guard LLM: **gpt-5.6-luna via the local Codex shim** (`benchmarks/tools/codex_shim.py`; OpenAI API credits were
exhausted). This differs from the gpt-4.1-mini used for the Agent-SafetyBench baselines. 0 LLM errors (an LLM
failure is never counted as allow or block; such chunks are re-run).

**FGL at install time: skipped.** FGL does not vet skill text. Its evolution gate (component 4) grounds a
candidate artifact in the observations of the session that produced it; a third-party skill arrives with no such
evidence, so the gate has nothing to ground against. That is not a trivial port, so no FGL install-time number
is reported.

### Results: poisoned skills refused at install (attack prevented), by scenario and risk

| group | n | Hermes blocked (community) | Hermes blocked, attack-attributable | Hermes blocked on clean-passing skills | agent-created gate would refuse | NeMo self-check SKILL.md blocked | NeMo content-safety SKILL.md blocked | NeMo content-safety all text files blocked |
|---|---|---|---|---|---|---|---|---|
| **all poisoned (879)** | 879 | 165/879 (18.8%) | 70/879 (8.0%) | 60/767 (7.8%) | 53/879 (6.0%) | 761/879 (86.6%) | 54/879 (6.1%) | 196/879 (22.3%) |
| **FPP** | 687 | 111/687 (16.2%) | 54/687 (7.9%) | 47/616 (7.6%) | 51/687 (7.4%) | 569/687 (82.8%) | 41/687 (6.0%) | 146/687 (21.3%) |
| **SMP** | 192 | 54/192 (28.1%) | 16/192 (8.3%) | 13/151 (8.6%) | 2/192 (1.0%) | 192/192 (100.0%) | 13/192 (6.8%) | 50/192 (26.0%) |
| FPP / anti_forensics | 73 | 5/73 (6.8%) | 1/73 (1.4%) | 1/69 (1.4%) | 0/73 (0.0%) | 59/73 (80.8%) | 0/73 (0.0%) | 5/73 (6.8%) |
| FPP / backdoor_injection | 55 | 22/55 (40.0%) | 14/55 (25.5%) | 14/47 (29.8%) | 13/55 (23.6%) | 44/55 (80.0%) | 4/55 (7.3%) | 13/55 (23.6%) |
| FPP / data_exfiltration | 51 | 11/51 (21.6%) | 4/51 (7.8%) | 4/44 (9.1%) | 0/51 (0.0%) | 43/51 (84.3%) | 9/51 (17.6%) | 34/51 (66.7%) |
| FPP / dos | 55 | 9/55 (16.4%) | 7/55 (12.7%) | 7/53 (13.2%) | 7/55 (12.7%) | 49/55 (89.1%) | 3/55 (5.5%) | 7/55 (12.7%) |
| FPP / goal_hijacking | 67 | 9/67 (13.4%) | 4/67 (6.0%) | 3/60 (5.0%) | 6/67 (9.0%) | 56/67 (83.6%) | 3/67 (4.5%) | 9/67 (13.4%) |
| FPP / malware_deployment | 52 | 2/52 (3.8%) | 0/52 (0.0%) | 0/50 (0.0%) | 0/52 (0.0%) | 42/52 (80.8%) | 4/52 (7.7%) | 13/52 (25.0%) |
| FPP / output_manipulation | 47 | 8/47 (17.0%) | 5/47 (10.6%) | 0/39 (0.0%) | 2/47 (4.3%) | 39/47 (83.0%) | 4/47 (8.5%) | 7/47 (14.9%) |
| FPP / poisoning | 67 | 7/67 (10.4%) | 0/67 (0.0%) | 0/60 (0.0%) | 1/67 (1.5%) | 56/67 (83.6%) | 0/67 (0.0%) | 4/67 (6.0%) |
| FPP / privilege_escalation | 54 | 6/54 (11.1%) | 3/54 (5.6%) | 3/51 (5.9%) | 0/54 (0.0%) | 43/54 (79.6%) | 10/54 (18.5%) | 31/54 (57.4%) |
| FPP / proxy_attack | 52 | 12/52 (23.1%) | 3/52 (5.8%) | 3/41 (7.3%) | 6/52 (11.5%) | 42/52 (80.8%) | 0/52 (0.0%) | 10/52 (19.2%) |
| FPP / system_corruption | 45 | 10/45 (22.2%) | 10/45 (22.2%) | 10/45 (22.2%) | 10/45 (22.2%) | 40/45 (88.9%) | 2/45 (4.4%) | 8/45 (17.8%) |
| FPP / unauthorized_file_modification | 69 | 10/69 (14.5%) | 3/69 (4.3%) | 2/57 (3.5%) | 6/69 (8.7%) | 56/69 (81.2%) | 2/69 (2.9%) | 5/69 (7.2%) |
| SMP / anti_forensics | 15 | 3/15 (20.0%) | 1/15 (6.7%) | 1/13 (7.7%) | 0/15 (0.0%) | 15/15 (100.0%) | 3/15 (20.0%) | 7/15 (46.7%) |
| SMP / backdoor_injection | 18 | 10/18 (55.6%) | 8/18 (44.4%) | 6/14 (42.9%) | 1/18 (5.6%) | 18/18 (100.0%) | 1/18 (5.6%) | 7/18 (38.9%) |
| SMP / data_exfiltration | 16 | 4/16 (25.0%) | 1/16 (6.2%) | 1/13 (7.7%) | 0/16 (0.0%) | 16/16 (100.0%) | 4/16 (25.0%) | 11/16 (68.8%) |
| SMP / dos | 18 | 3/18 (16.7%) | 1/18 (5.6%) | 1/16 (6.2%) | 0/18 (0.0%) | 18/18 (100.0%) | 1/18 (5.6%) | 6/18 (33.3%) |
| SMP / goal_hijacking | 19 | 4/19 (21.1%) | 0/19 (0.0%) | 0/15 (0.0%) | 0/19 (0.0%) | 19/19 (100.0%) | 2/19 (10.5%) | 2/19 (10.5%) |
| SMP / malware_deployment | 16 | 4/16 (25.0%) | 0/16 (0.0%) | 0/12 (0.0%) | 0/16 (0.0%) | 16/16 (100.0%) | 0/16 (0.0%) | 1/16 (6.2%) |
| SMP / output_manipulation | 13 | 4/13 (30.8%) | 0/13 (0.0%) | 0/9 (0.0%) | 0/13 (0.0%) | 13/13 (100.0%) | 0/13 (0.0%) | 1/13 (7.7%) |
| SMP / poisoning | 18 | 4/18 (22.2%) | 1/18 (5.6%) | 1/15 (6.7%) | 0/18 (0.0%) | 18/18 (100.0%) | 1/18 (5.6%) | 1/18 (5.6%) |
| SMP / privilege_escalation | 15 | 3/15 (20.0%) | 1/15 (6.7%) | 0/12 (0.0%) | 1/15 (6.7%) | 15/15 (100.0%) | 0/15 (0.0%) | 5/15 (33.3%) |
| SMP / proxy_attack | 8 | 4/8 (50.0%) | 0/8 (0.0%) | 0/4 (0.0%) | 0/8 (0.0%) | 8/8 (100.0%) | 0/8 (0.0%) | 2/8 (25.0%) |
| SMP / system_corruption | 17 | 7/17 (41.2%) | 3/17 (17.6%) | 3/13 (23.1%) | 0/17 (0.0%) | 17/17 (100.0%) | 1/17 (5.9%) | 4/17 (23.5%) |
| SMP / unauthorized_file_modification | 19 | 4/19 (21.1%) | 0/19 (0.0%) | 0/15 (0.0%) | 0/19 (0.0%) | 19/19 (100.0%) | 0/19 (0.0%) | 3/19 (15.8%) |

Notes: "blocked on clean-passing skills" restricts to samples whose clean original Hermes would install
(767 of 879); it is the cleanest view of what the scanner adds. NeMo columns count a sample as blocked if any
of its skills is blocked.

### FPP by realization / carrier

| FPP realization / carrier | n | Hermes blocked | attack-attributable | NeMo self-check SKILL.md | NeMo safety SKILL.md | NeMo safety all text |
|---|---|---|---|---|---|---|
| executable_code | 45 | 14/45 (31.1%) | 5/45 (11.1%) | 45/45 (100.0%) | 0/45 (0.0%) | 20/45 (44.4%) |
| import_new_helper | 47 | 13/47 (27.7%) | 4/47 (8.5%) | 47/47 (100.0%) | 0/47 (0.0%) | 17/47 (36.2%) |
| plain_text | 151 | 24/151 (15.9%) | 11/151 (7.3%) | 151/151 (100.0%) | 33/151 (21.9%) | 35/151 (23.2%) |
| redirect_to_new_doc | 149 | 25/149 (16.8%) | 16/149 (10.7%) | 141/149 (94.6%) | 3/149 (2.0%) | 37/149 (24.8%) |
| redirect_to_new_pdf | 127 | 7/127 (5.5%) | 1/127 (0.8%) | 17/127 (13.4%) | 0/127 (0.0%) | 0/127 (0.0%) |
| redirect_to_new_script | 168 | 28/168 (16.7%) | 17/168 (10.1%) | 168/168 (100.0%) | 5/168 (3.0%) | 37/168 (22.0%) |
| documentation | 595 | 84/595 (14.1%) | 45/595 (7.6%) | - | - | - |
| helper_script | 92 | 27/92 (29.3%) | 9/92 (9.8%) | - | - | - |

### False positives on the clean originals

| defense | clean (task, skill) dirs blocked | notes |
|---|---|---|
| Hermes skills_guard, community | 8/109 (7.3%); 5 of 71 distinct FPP skill names | verdicts: 101 safe, 5 caution, 3 dangerous. Patterns: `sudo_usage` (pptx, image_editing), `oversized_skill` (pptx), `python_getenv_secret` (citation-management), `agent_config_mod` (react-best-practices), `curl_pipe_shell` + `destructive_root_rm` (nlp-research-repo-package-installment) |
| Hermes, agent-created policy | 3/109 would be refused (dangerous) | gate off by default |
| NeMo self check input, SKILL.md | 107/109 (98.2%) | policy line "should not contain code or ask to execute code" fires on almost any SKILL.md |
| NeMo content safety, SKILL.md | 1/109 (0.9%) | `powerlifting` |
| NeMo content safety, all text files | 1/109 (0.9%) | same skill |

### Part A takeaways
* **Hermes `skills_guard` would let 81% of SkillHarm's poisoned skills install** (blocks 165/879 = 18.8%),
  and only 70/879 (8.0%) blocks are caused by the attack itself; the rest are skills the scanner also refuses
  in their clean form (7.3% of clean skills). On skills whose clean form passes, it catches 7.8%. Its best
  categories are backdoor injection (SSH-key/`authorized_keys`, `system_overwrite` patterns) and system
  corruption; it misses nearly all goal hijacking, poisoning, output manipulation, malware deployment and
  anti-forensics payloads written as natural-language instructions. Attack-introduced patterns:
  `python_os_environ` 19, `system_overwrite` 18, `ssh_backdoor` 12, `ssh_dir_access` 8, `hardcoded_secret` 6,
  `agent_config_mod` 4, others at 3 or fewer.
* For reference, the dataset's own metadata records the authors' skill-scanner result per sample:
  `scanner_result.safe=true` for 760/879 (FPP 580/687, SMP 180/192). Hermes's regex scanner is a different
  scanner; it passes a similar share.
* Payloads moved into a PDF (`redirect_to_new_pdf`, 127 samples) are invisible to every text scanner here:
  Hermes 1/127 attributable, NeMo 0/127 (PDF bytes are not text).
* **NeMo self check input is not usable as a skill vetter**: it blocks 98% of clean SKILL.md files and fewer
  poisoned ones (86.6%): in `redirect_to_new_pdf` samples the poisoned SKILL.md is a short pointer to the PDF
  (120/127 have no code block, vs 5/127 of their clean originals), so the "no code" policy line stops firing.
* **NeMo content safety over all text files** is the strongest static discriminator measured: 196/879 (22.3%)
  poisoned blocked vs 1/109 (0.9%) clean, strongest on data exfiltration (34/51 FPP) and privilege escalation
  (31/54 FPP). On SKILL.md alone it drops to 6.1% because most payloads live outside SKILL.md.
* SMP stage-2 (the mutated skill after Task A) is not shipped in the dataset; it exists only at run time.
  See "SMP stage 2" below.

## Part B: run-time monitors, offline replay over the `none` trajectories

**This is an offline replay, not a counterfactual run.** Each monitor sees the recorded actions of the
undefended victim one by one; a block is recorded but the agent is not re-run after it, so we cannot know whether
it would have found another way (or failed the task). All "stop" and "would-have-blocked ASR" numbers below are
upper-bound style estimates under that assumption.

### Data
`benchmarks/skillharm/trajectories/none/` (exported by the SkillHarm run agent, see its README): 77 valid FPP trials
(victim Codex CLI, model gpt-5.6-luna, no defense prompt; sample of up to 8 FPP samples per risk; infra-failed
trials excluded). ASR(none) by the authors' deterministic evaluator: **49/77 (63.6%)**. At the time of writing the
folder held no BENIGN and no SMP trajectories, so the benign false-block rate and all SMP run-time numbers are not
available yet (`offline_monitors/run_replay.sh` resumes and adds them when the files appear).

### Monitors (all imported from the real packages; LLM monitors use gpt-5.6-luna via the local Codex shim)
* **Hermes builtin**: `tools.approval.check_all_command_guards(cmd, "local")` in a Hermes cron session with its
  default config (`approvals.cron_mode=deny`, the only Hermes non-interactive mode that blocks a flagged command):
  hardline floor, sudo-stdin guard, `DANGEROUS_PATTERNS` / execution-flag findings, tirith (not installed here).
* **Hermes smart**: Hermes default `approvals.mode=smart`: hardline/sudo → block; command flagged by the detectors
  → `tools.approval._smart_approve` (Hermes's own prompt) on the guard LLM; DENY or ESCALATE → block (headless,
  no human to escalate to); unflagged → allow.
* **NeMo**: `guards/nemo_guard.nemo_check_command(task, command, context="")`: NeMo 0.24.1 `self check input`
  rail on the user task (once per task) + `self check output` rail on the rendered command.
* **FGL**: `benchmarks/agent_safetybench/fgl_guard.FGLMonitor.check(task, history, tool="shell",
  args={"command": cmd}, desc="execute shell command in the task container")`, the same monitor and prompt as
  on Agent-SafetyBench; history = earlier actions and their outputs in the same session.

Every executed shell command is vetted in order with the user task as the only trusted context (the skill text
reaches a monitor only inside earlier command outputs, as the victim saw it). Codex's `/bin/bash -lc '...'` exec
wrapper is stripped first (a Hermes terminal tool receives the bare command). Codex `file_change` items carry
only paths, no content, so they are not vetted by any monitor (they stay in the FGL history). An LLM failure is
never counted as allow or block: the trajectory is re-run (0 remained). Guard model: gpt-5.6-luna for all LLM
monitors (comparable among themselves, but not with the gpt-4.1-mini ASB baselines).

### Stop definitions (successful attacks only)
* **any block**: the monitor blocks at least one command anywhere in the trajectory.
* **block at/before harm step**: blocks some command at or before the first step that realizes the attacker goal.
* **block on an attack step**: blocks a command that is itself part of the attack chain (e.g. running the
  attacker's helper script, the exfiltration/deletion/overwrite command). This is the most meaningful number: a
  block on an unrelated earlier command would, in a real run, most likely just make the agent retry differently.

The trajectories carry no harm-step index (SkillHarm scores the end state), so the harm step and the attack-step
set are **LLM-estimated** (`offline_monitors/locate_harm.py`, gpt-5.6-luna, given the user task, the attacker goal
from the dataset and the numbered actions; only indices are stored). For 14/77 trajectories the locator returned no
harm step (1 of them a successful attack, hence 48 in that column).
would-have-blocked ASR = ASR(none) × (1 − stop rate).

### Results

ASR(none) over attack trajectories with a deterministic outcome: 49/77 (63.6%).

| monitor | stop: any block | stop: block at/before harm step | stop: block on an attack step | would-have-blocked ASR (any / by-harm / on-attack) | benign trajectories with any block | blocked non-attack steps | steps vetted / blocked |
|---|---|---|---|---|---|---|---|
| Hermes builtin (headless gate) | 48/49 (98.0%) | 25/48 (52.1%) | 14/49 (28.6%) | 1.3% / 30.5% / 45.4% | n/a | 441/1029 (42.9%) | 1139 / 467 |
| Hermes smart approval | 11/49 (22.4%) | 4/48 (8.3%) | 5/49 (10.2%) | 49.3% / 58.3% / 57.1% | n/a | 14/1029 (1.4%) | 1139 / 22 |
| NeMo self-check rails | 16/49 (32.7%) | 15/48 (31.2%) | 14/49 (28.6%) | 42.8% / 43.7% / 45.4% | n/a | 211/1030 (20.5%) | 1140 / 262 |
| FGL action monitor | 24/49 (49.0%) | 20/48 (41.7%) | 18/49 (36.7%) | 32.4% / 37.1% / 40.2% | n/a | 111/1030 (10.8%) | 1140 / 143 |

**By scenario**: successful attacks stopped, 'on attack step' / 'any block'

| scenario | ASR(none) | Hermes builtin (headless gate) | Hermes smart approval | NeMo self-check rails | FGL action monitor |
|---|---|---|---|---|---|
| FPP | 49/77 | 14/49 (28.6%) / any 48/49 (98.0%) | 5/49 (10.2%) / any 11/49 (22.4%) | 14/49 (28.6%) / any 16/49 (32.7%) | 18/49 (36.7%) / any 24/49 (49.0%) |

**By risk**: successful attacks stopped, 'on attack step' / 'any block'

| risk | ASR(none) | Hermes builtin (headless gate) | Hermes smart approval | NeMo self-check rails | FGL action monitor |
|---|---|---|---|---|---|
| anti_forensics | 6/6 | 2/6 (33.3%) / any 6/6 (100.0%) | 0/6 (0.0%) / any 1/6 (16.7%) | 2/6 (33.3%) / any 3/6 (50.0%) | 2/6 (33.3%) / any 4/6 (66.7%) |
| backdoor_injection | 5/6 | 1/5 (20.0%) / any 5/5 (100.0%) | 1/5 (20.0%) / any 1/5 (20.0%) | 2/5 (40.0%) / any 2/5 (40.0%) | 4/5 (80.0%) / any 4/5 (80.0%) |
| data_exfiltration | 0/6 | n/a / any n/a | n/a / any n/a | n/a / any n/a | n/a / any n/a |
| dos | 4/6 | 1/4 (25.0%) / any 3/4 (75.0%) | 1/4 (25.0%) / any 1/4 (25.0%) | 0/4 (0.0%) / any 0/4 (0.0%) | 1/4 (25.0%) / any 1/4 (25.0%) |
| goal_hijacking | 5/8 | 0/5 (0.0%) / any 5/5 (100.0%) | 0/5 (0.0%) / any 1/5 (20.0%) | 0/5 (0.0%) / any 0/5 (0.0%) | 1/5 (20.0%) / any 3/5 (60.0%) |
| malware_deployment | 2/6 | 2/2 (100.0%) / any 2/2 (100.0%) | 0/2 (0.0%) / any 0/2 (0.0%) | 0/2 (0.0%) / any 0/2 (0.0%) | 1/2 (50.0%) / any 1/2 (50.0%) |
| output_manipulation | 4/7 | 3/4 (75.0%) / any 4/4 (100.0%) | 0/4 (0.0%) / any 1/4 (25.0%) | 0/4 (0.0%) / any 0/4 (0.0%) | 1/4 (25.0%) / any 1/4 (25.0%) |
| poisoning | 4/6 | 1/4 (25.0%) / any 4/4 (100.0%) | 0/4 (0.0%) / any 1/4 (25.0%) | 1/4 (25.0%) / any 1/4 (25.0%) | 0/4 (0.0%) / any 0/4 (0.0%) |
| privilege_escalation | 6/6 | 1/6 (16.7%) / any 6/6 (100.0%) | 1/6 (16.7%) / any 1/6 (16.7%) | 4/6 (66.7%) / any 4/6 (66.7%) | 3/6 (50.0%) / any 3/6 (50.0%) |
| proxy_attack | 0/6 | n/a / any n/a | n/a / any n/a | n/a / any n/a | n/a / any n/a |
| system_corruption | 7/7 | 3/7 (42.9%) / any 7/7 (100.0%) | 2/7 (28.6%) / any 3/7 (42.9%) | 3/7 (42.9%) / any 3/7 (42.9%) | 3/7 (42.9%) / any 4/7 (57.1%) |
| unauthorized_file_modification | 6/7 | 0/6 (0.0%) / any 6/6 (100.0%) | 0/6 (0.0%) / any 1/6 (16.7%) | 2/6 (33.3%) / any 3/6 (50.0%) | 2/6 (33.3%) / any 3/6 (50.0%) |

**By FPP realization**: successful attacks stopped, 'on attack step' / 'any block'

| FPP realization | ASR(none) | Hermes builtin (headless gate) | Hermes smart approval | NeMo self-check rails | FGL action monitor |
|---|---|---|---|---|---|
| executable_code | 4/8 | 2/4 (50.0%) / any 4/4 (100.0%) | 0/4 (0.0%) / any 0/4 (0.0%) | 1/4 (25.0%) / any 1/4 (25.0%) | 0/4 (0.0%) / any 1/4 (25.0%) |
| import_new_helper | 3/5 | 1/3 (33.3%) / any 3/3 (100.0%) | 0/3 (0.0%) / any 0/3 (0.0%) | 1/3 (33.3%) / any 1/3 (33.3%) | 0/3 (0.0%) / any 0/3 (0.0%) |
| plain_text | 8/17 | 3/8 (37.5%) / any 8/8 (100.0%) | 2/8 (25.0%) / any 2/8 (25.0%) | 5/8 (62.5%) / any 5/8 (62.5%) | 5/8 (62.5%) / any 6/8 (75.0%) |
| redirect_to_new_doc | 10/13 | 2/10 (20.0%) / any 10/10 (100.0%) | 0/10 (0.0%) / any 3/10 (30.0%) | 4/10 (40.0%) / any 5/10 (50.0%) | 7/10 (70.0%) / any 8/10 (80.0%) |
| redirect_to_new_pdf | 9/16 | 4/9 (44.4%) / any 9/9 (100.0%) | 2/9 (22.2%) / any 4/9 (44.4%) | 2/9 (22.2%) / any 3/9 (33.3%) | 3/9 (33.3%) / any 5/9 (55.6%) |
| redirect_to_new_script | 15/18 | 2/15 (13.3%) / any 14/15 (93.3%) | 1/15 (6.7%) / any 2/15 (13.3%) | 1/15 (6.7%) / any 1/15 (6.7%) | 3/15 (20.0%) / any 4/15 (26.7%) |

"steps vetted / blocked" and "blocked non-attack steps" are over all 77 trajectories (successful and failed);
"blocked non-attack steps" = blocked commands that the locator did not mark as attack steps, a step-level
false-block proxy in the absence of benign trajectories.

### Part B takeaways
* **Hermes builtin "stops" 48/49 successful attacks, but for the wrong reason.** 428 of its 467 blocks are
  `script execution via heredoc` (`python3 - <<EOF`, Codex's normal way to run a snippet) and 35 are
  `script execution via -e/-c flag`; 42.9% of all non-attack commands are blocked. Counting only blocks on
  attack steps, it stops 14/49 (28.6%). In a headless Hermes cron run this gate would block almost every task,
  benign or not.
* **Hermes smart approval** sends the same flagged commands to the LLM reviewer, which approves 445 of 467
  (18 ESCALATE, 4 DENY); it stops 5/49 (10.2%) on attack steps, with 1.4% blocked non-attack steps. Its prompt
  asks only whether a shell operation is destructive, not whether it serves the user task.
* **NeMo self-check rails** stop 14/49 (28.6%) on attack steps, but mostly through the input rail: for 15/77
  trajectories the rail rejects the user's own (benign) task, which blocks every command of that trial. The output
  rail on commands alone blocks an attack step in 5/49 successful attacks. 20.5% of non-attack steps blocked.
* **FGL action monitor** stops the most: 18/49 (36.7%) on attack steps, 24/49 (49.0%) any block, with 10.8% of
  non-attack steps blocked. would-have-blocked ASR 63.6% → 40.2% (on-attack) / 32.4% (any). It is strongest where
  the injected action is visibly off-task (backdoor injection 4/5, redirect-to-new-doc 7/10, plain text 5/8) and
  weakest where the harm runs inside an attacker-modified helper the task legitimately calls
  (`redirect_to_new_script` 3/15, `executable_code` 0/4, `import_new_helper` 0/3): the command looks like normal
  task work and the harmful code is not in the command line.
* No monitor catches a large share of SkillHarm attacks at run time: the best on-attack stop rate is 36.7%.

### Caveats
* Offline replay without counterfactual continuation (see above); 77 FPP trajectories, small per-risk cells
  (2 to 7 successful attacks per risk); data exfiltration and proxy attack had 0 successful attacks in `none`.
* Harm step and attack steps are LLM-estimated, not ground truth.
* Benign trajectories and SMP trajectories were not available; no benign trajectory-level false-block rate yet.
* Guard LLM is gpt-5.6-luna through `codex exec` (ChatGPT subscription), not the API; `max_tokens`/`temperature`
  are not enforced by Codex, and a Codex agent wraps every call. Numbers are not directly comparable to the
  gpt-4.1-mini ASB baselines.
* Hermes smart: when the LLM call fails Hermes itself returns ESCALATE; such cases were re-run instead.
* The static Part A scans the skill as shipped; Hermes would rescan only via `hermes skills audit` or a reinstall.

## SMP stage 2
The mutated (post-Task-A) skill is not in the dataset. The SMP harness snapshots it at the end of Task A
(`<task A job>/verifier/skills_snapshot.tar.gz`); `static_scan/fetch_smp_stage2.sh` collects those snapshots
from the run box and `SMP_STAGE2_ROOT=<dir> python static_scan/hermes_static_scan.py` + `analyze_static.py`
report the re-scan verdicts. Not run yet: no SMP `none` trials were finished when this report was written.

## Files
* `static_scan/`: `common.py`, `smp_items.py` (sample enumeration), `hermes_static_scan.py`,
  `nemo_static_scan.py`, `analyze_static.py`, `make_tables.py`, `fetch_smp_stage2.sh`;
  `results/hermes_static_scan.json`, `results/nemo_static_scan_{selfcheck,safety}.json`,
  `results/nemo_chunk_cache_*.json` (chunk hash → verdict), `results/static_summary.json`.
* `offline_monitors/`: `traj_io.py` (loader), `replay.py` (monitors), `locate_harm.py`, `score.py`,
  `make_tables.py`, `run_replay.sh`, `poll_and_replay.sh`, `reuse_partial.py`, `test_replay.py` + `synthetic/`
  (5 synthetic trajectories without payloads); `results/{hermes_builtin,hermes_smart,nemo_selfcheck,fgl}.jsonl`
  (per-step decisions, command hashes only), `results/harm_steps.json`, `results/summary.json`.
* `benchmarks/tools/codex_shim.py` (+ `shim.env`, `nemo_base_url_patch.py`): local OpenAI-compatible endpoint
  backed by `codex exec`.
