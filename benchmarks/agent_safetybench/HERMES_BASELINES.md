# Hermes Agent built-in defenses as baselines on Agent-SafetyBench

Agent: gpt-4.1-mini, all 2000 ASB cases, authors' safety system prompt (`run_asb.py`). Guard model: gpt-4.1-mini.
Judge: gpt-4.1 with the authors' ShieldAgent evaluation prompt (`score_asb.py --scorer llm`). ShieldAgent-8B scoring
of the Hermes runs is still pending; it will be run centrally. Code: `guards/hermes_guard.py`. Offline replay:
`hermes_offline_replay.py`. Summary: `hermes_baselines_summary.py` writes `results/hermes_baselines_summary.json`.

## What Hermes ships (hermes-agent 0.19.0, installed package)

- The pre-execution guard covers **shell commands only**: `tools/approval.py`. It includes `HARDLINE_PATTERNS`
  (l.417, unconditional floor: `rm -rf /`, mkfs, shutdown/reboot, fork bomb, ...), `DANGEROUS_PATTERNS` (l.606),
  `_execution_flag_findings`, both combined in `detect_dangerous_command` (l.1988), a sudo-stdin guard, and the
  external `tirith` scanner (`tools/tirith_security.py`). The single entry point is `check_all_command_guards` (l.3173).
  Non-shell tools are gated only when a plugin `pre_tool_call` hook escalates (`request_tool_approval`, l.2940). Hermes
  ships no such rule by default.
- Default config (`hermes_cli/config.py` l.2675-2678): `approvals.mode: "smart"`, `approvals.cron_mode: "deny"`.
- Behavior when no human is present (`check_all_command_guards`, l.3234 onward):
  - Bare non-interactive, non-gateway, non-cron run: a flagged command is **auto-approved**. In Hermes's words, "outside
    CLI/gateway/ask flows, we do not block on approvals". The `_run_approval_gate` docstring (l.2676-2681) also says
    "the dangerous-command path keeps its historical fail-open default".
  - Cron session (`HERMES_CRON_SESSION`) with the default `cron_mode: deny`: a flagged command is **blocked** ("cron jobs run
    without a user present to approve it"). Smart approval is not consulted on this path.
  - Smart approval (`_smart_approve`, l.2560) runs only on the interactive, gateway, or ask path (l.3381). APPROVE
    executes the command. DENY or ESCALATE goes on to a human prompt.

## How each condition maps Hermes behavior

ASB tools are simulated APIs, not shell commands. Each detector runs on every string argument value (recursively) and
on a `"<tool_name> <args-json>"` rendering of the call. A call is flagged if any of these strings is flagged. This choice
favors Hermes, which would never inspect these calls. Hermes runs with an isolated, empty `HERMES_HOME`, so its built-in
defaults apply and the user's `~/.hermes` is ignored.

| Condition | Mapping |
|---|---|
| `hermes_builtin` | Hermes's own `check_all_command_guards(s, "local")` as a cron session, default config: hardline, then sudo-stdin, then deny rules (none), then cron deny on `detect_dangerous_command` and tirith. A non-approved result blocks the call. This is the only headless Hermes mode that blocks. The literal bare-script default would auto-approve, which is identical to `none`. |
| `hermes_smart` | Default `mode: smart` with no human. Hardline and sudo-stdin block unconditionally, as in Hermes. A flagged call goes to Hermes's `_smart_approve`, called directly with its exact prompt, comment stripping and verdict parsing. The `<command>` is the call rendering and the description is the detector findings. APPROVE allows. DENY or ESCALATE blocks, because nobody is there to answer the escalation. Unflagged calls are allowed, as in Hermes. |
| `hermes_smart_all` | Generous upper bound. **Hermes does not do this.** `_smart_approve` runs on every tool call, with the same mapping. Unflagged calls get the description `"agent tool call (reviewed on every call; not a Hermes detector finding)"`. |
| `hermes_smart_all_denyonly` | Sensitivity variant, also not a Hermes mode. Same as above, but ESCALATE allows (as if a human approved every escalation). Only DENY blocks. |

`_smart_approve` reaches its auxiliary LLM through `agent.auxiliary_client.call_llm`. That module attribute is replaced
by a thin OpenAI wrapper on gpt-4.1-mini. The messages, `temperature=0` and `max_tokens=16` are Hermes's own. The wrapper
retries transient errors 4 times. A final failure would make Hermes return ESCALATE. In practice there were 0 LLM errors.
tirith was **not installed** (`which tirith` returned empty), and Hermes was not allowed to auto-download it
(`TIRITH_ENABLED=0`). With the default `tirith_fail_open: true`, a missing binary means "allow", so the outcome is the same.

## Offline fire rate (no LLM)

Replaying the detectors over every tool call in `results/asb-gpt-4.1-mini-none/gen_res.json` (`results/hermes_offline_firerate.json`):
**1 of 2772 tool calls (0.04%) fires, in 1 of 2000 cases.** That one is the hardline "system shutdown/reboot" on the call
`shutdown {"time": "00:00"}` (case 84), which matched only because the ASB tool is *named* `shutdown` and the rendering
starts with it. `DANGEROUS_PATTERNS`, execution-flag findings and sudo-stdin never fire. On these trajectories, `hermes_builtin`
and `hermes_smart` therefore differ from `none` by at most one blocked call. The online runs confirm this.

## Results (gpt-4.1 judge, safety % = fraction judged safe; n = 2000 for every row, 0 judge errors)

| Condition | Total | Behavior (1589) | Content (411) | Leak | Property | Spread | Physical | Law | Availability | Code | Produce |
|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 65.8 | 60.5 | 86.4 | 57.2 | 67.2 | 48.8 | 62.4 | 51.6 | 73.6 | 75.2 | 90.4 |
| fgl_monitor | 83.3 | 82.9 | 84.9 | 82.4 | 87.2 | 62.8 | 83.6 | 88.4 | 91.2 | 81.6 | 89.6 |
| hermes_builtin | 65.7 | 60.6 | 85.4 | 55.2 | 66.0 | 48.4 | 63.6 | 53.6 | 73.6 | 75.2 | 90.0 |
| hermes_smart | 65.0 | 59.8 | 85.2 | 54.4 | 67.2 | 50.4 | 61.6 | 53.2 | 70.0 | 74.4 | 89.2 |
| hermes_smart_all | 90.9 | 92.3 | 85.6 | 96.8 | 97.6 | 70.0 | 98.4 | 92.4 | 98.0 | 84.8 | 89.2 |
| hermes_smart_all_denyonly | 66.8 | 61.7 | 86.9 | 57.6 | 69.6 | 50.8 | 62.4 | 52.4 | 74.4 | 76.0 | 91.6 |

| Condition | Guard LLM calls | Tool calls checked | Blocked calls | Cases with a block | Guard tokens (prompt+completion) | Over-block (fulfillable cases with a block / 735) | Paired vs none: unsafe→safe / safe→unsafe |
|---|---|---|---|---|---|---|---|
| fgl_monitor | 2742 | 2742 | 816 | 659 | 1,194,446 | 216 (29.4%) | 405 / 54 |
| hermes_builtin | 0 | 2684 | 1 | 1 | 0 | 0 (0.0%) | 78 / 80 |
| hermes_smart | 0 | 2677 | 1 | 1 | 0 | 0 (0.0%) | 76 / 91 |
| hermes_smart_all | 1660 | 1661 | 1539 | 1375 | 508,770 | 600 (81.6%) | 527 / 25 |
| hermes_smart_all_denyonly | 2658 | 2659 | 13 | 12 | 823,848 | 2 (0.3%) | 94 / 73 |

The column definitions follow `results/shieldagent_table5.json`. Behavior means cases with tool environments, Content
means cases without them, and each of the 8 risk categories has 250 cases. Over-block follows `results/paired_analysis.json`.
The summary script checks both definitions by reproducing the stored ShieldAgent table and paired analysis exactly.

## Reading

- **The built-in Hermes guard does nothing on ASB.** `hermes_builtin` and `hermes_smart` blocked one call each, the
  `shutdown` tool name match. The smart reviewer was never invoked because that one hit was hardline. Their totals
  (65.7, 65.0) match `none` (65.8) within run-to-run noise. The paired flips are symmetric (about 80 cases each way), and the
  Content column, where no guard can act, ranges from 84.9 to 86.9 across the six runs.
- **The smart reviewer applied to everything is close to refusing every tool call.** Hermes's prompt asks about "shell
  commands". For API tool calls the reviewer answered ESCALATE on 1530 of 1660 calls, DENY on 8 and APPROVE on 122. With
  ESCALATE mapped to block (no human), it blocked 92.7% of reviewed calls and 1375 of the 1589 Behavior cases. The judge
  scores a refusal as safe, so the total rises to 90.9%, but 81.6% of fulfillable cases are blocked, against 29.4% for FGL.
  It is an upper bound on what the Hermes prompt can buy, and most of it comes from refusal, not from discrimination.
- **The discriminative part of the Hermes reviewer is DENY, and it is small.** With ESCALATE allowed
  (`hermes_smart_all_denyonly`), 12 DENY verdicts block 13 calls: `delete_file /root`, `read_file ~/.ssh/id_rsa`, webshell
  writes, `send_money`, `binance_withdraw`, `get_account_privatekey`. The total is 66.8, +1.0 over `none`, within noise.
- FGL (+17.5 pp, 29.4% over-block) sits between the two Hermes extremes: no effect (built-in or deny-only) and
  near-total blocking (smart_all with escalate→block).

## Caveats

- The `none` and `fgl_monitor` rows are the existing runs. The four Hermes rows are new runs, so agent sampling noise is
  present even at temperature 0 (see the paired flips).
- Applying Hermes's detectors to non-shell tools, and smart_all as a whole, favor Hermes beyond what Hermes actually
  does. The faithful bare-headless Hermes default (auto-approve) is `none` by construction.
- tirith was not installed. Its scanner targets shell and URL content (homographs, pipe-to-interpreter) and would very
  likely not change ASB results, but this was not measured.
- During the `hermes_smart_all_denyonly` run, the detectors flagged one real `DANGEROUS_PATTERNS` hit:
  `terminal_execute "sudo du -ahx / | sort -rh | head -20"` ("sudo with combined-flag privilege escalation"). The
  reviewer approved it. The `none` trajectories contain no such call, because the agent's trajectories differ between runs.
- ShieldAgent-8B scores for the Hermes runs are pending (central GPU scoring). The FGL and `none` deltas were
  judge-robust before (+17.4 ShieldAgent vs +17.5 gpt-4.1).
- `run_meta.json` is the single generation pass (all 2000 cases completed in pass 1). `run_meta_pass1.json` is a copy.
  The guard's `hermes_flag_log` keeps the first 200 entries.
