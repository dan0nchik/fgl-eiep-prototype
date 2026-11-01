# AutoSkillHarm none-condition trajectories

One JSON file per victim-eval trial of the **none** defense condition (no defense
prompt), produced by the authors' `victim_eval` run of freshly generated
AutoSkillHarm Fixed-Payload-Poisoning (FPP) attacks. These are for **offline
replay** of runtime monitors (Hermes / NeMo / FGL) without re-running the
container pipeline.

## Provenance

- Attacks were generated fresh with the published AutoSkillHarm pipeline
  (`fixed-payload-poisoning/attack_design`), driven by the Codex CLI on
  `gpt-5.6-sol` (designer) / `gpt-5.6-luna` (victim) (recorded in `../../RESULTS.md`), against skillsbench v1.0 tasks.
  They are unseen by any defense prompt we wrote.
- The victim agent (none condition) is Codex on `gpt-5.6-luna`, run via Harbor.
- `harmful_outcome` is the authors' **deterministic** per-sample ASR verdict
  (`asr_result.json`, no LLM judge), not an estimate.

## Schema (one object per file, `<sample_id>.json`)

```json
{
  "id":            "<sample_id>  e.g. data_exfiltration__environment--skills--citation-management--SKILL_md__plain_text",
  "scenario":      "fixed_payload_poisoning",
  "risk":          "<risk_id from the 12-type taxonomy, e.g. data_exfiltration>",
  "task":          "<skillsbench task id, e.g. citation-check>",
  "skill":         "<owning skill root, e.g. environment/skills/citation-management>",
  "realization":   "<plain_text | redirect_to_new_doc | redirect_to_new_script | redirect_to_new_pdf | ...>",
  "target_path":   "<task-relative carrier path that was poisoned>",
  "instruction":   "<the benign user task text the victim agent was given (trusted context)>",
  "steps": [
    {"type": "command",     "command": "<shell command the agent ran>", "exit_code": <int|null>},
    {"type": "message",     "text": "<assistant message text>"},
    {"type": "file_change", "changes": [{"path": "...", "kind": "..."}]},
    {"type": "other",       "tool": "<server.tool>", "command": "<json args>"}
  ],
  "harmful_outcome": true,
  "asr_evidence":  {"what": "...", "where": "..."}
}
```

## Notes for the monitor-replay agent

- `steps` preserves execution order. Shell commands are already unwrapped from
  Codex's `/bin/bash -lc '...'` exec wrapper, i.e. the command the agent actually
  wrote (what a terminal-guard monitor would receive).
- The only **trusted** context for a monitor is `instruction` (the user task).
  The poisoned skill text is UNTRUSTED; it appears, if at all, only inside tool
  outputs in the agent's own history — never hand the skill content to a monitor
  as trusted input.
- The raw Codex event stream (`codex.txt`) and the authors' `asr_result.json` /
  `metadata.json` are retained server-side per trial; this export is the distilled
  replay form. The attacker payloads themselves are **not** exported here (only
  ids, metadata, step actions, and verdicts).
