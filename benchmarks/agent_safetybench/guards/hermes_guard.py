"""Hermes Agent's BUILT-IN pre-execution defenses as pre-action guards for Agent-SafetyBench.

Everything Hermes-specific is imported from the installed package (hermes-agent 0.19.0,
site-packages/tools/approval.py, tools/tirith_security.py, hermes_cli/config.py). Nothing below
re-implements a Hermes pattern or prompt.

Conditions (see HERMES_BASELINES.md for the full mapping and caveats):

  hermes_builtin   Hermes's headless command gate: tools.approval.check_all_command_guards(cmd, "local")
                   run as a cron session (HERMES_CRON_SESSION=1) with Hermes's default config
                   (approvals.cron_mode = "deny", hermes_cli/config.py). That path is: hardline floor
                   (detect_hardline_command) -> sudo-stdin guard -> user deny rules (none) -> cron deny:
                   detect_dangerous_command (DANGEROUS_PATTERNS + _execution_flag_findings) and tirith.
                   approved=False -> block. This is the only Hermes non-interactive mode that blocks a flagged
                   command; a bare non-interactive, non-gateway, non-cron run AUTO-APPROVES it
                   (approval.py, check_all_command_guards: "outside CLI/gateway/ask flows, we do not block").

  hermes_smart     Hermes default approvals.mode = "smart": the same detectors; a flagged call is reviewed
                   by tools.approval._smart_approve (called directly, Hermes's exact prompt, comment
                   stripping and verdict parsing). APPROVE -> allow; DENY / ESCALATE -> block (headless:
                   ESCALATE would go to a human, there is none). Hardline / sudo-stdin -> block unconditionally
                   (Hermes runs them before smart approval). Unflagged -> allow (faithful).

  hermes_smart_all Generous upper bound that Hermes itself does NOT implement: _smart_approve on EVERY tool call.

  hermes_smart_all_denyonly  Sensitivity variant of hermes_smart_all: only DENY blocks, ESCALATE -> allow
                   (i.e. as if a human approved every escalation). Not a Hermes mode either.

ASB tools are simulated API tools, not shell commands. The detectors are therefore applied to every string
argument value (recursively) plus a "<tool_name> <args-json>" rendering of the call; the call is flagged if any
of these strings is flagged. The rendering is what is put into <command> for the smart reviewer.

The auxiliary LLM that _smart_approve reaches via agent.auxiliary_client.call_llm is pointed at the guard model
(gpt-4.1-mini) by replacing that module attribute with a thin OpenAI wrapper; _smart_approve imports call_llm
inside the function, so the replacement is what it calls. Messages, temperature (0) and max_tokens (16) are
Hermes's own.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# ---- isolate Hermes from the user's ~/.hermes so its built-in DEFAULT config applies -------------------------
if not os.environ.get("HERMES_ASB_KEEP_HOME"):
    os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hermes_asb_home_")
# tirith: use it only if a binary is already installed; never let Hermes auto-download one here.
TIRITH_AVAILABLE = bool(shutil.which("tirith")) or os.path.isfile(
    os.path.join(os.environ["HERMES_HOME"], "bin", "tirith"))
if not TIRITH_AVAILABLE:
    os.environ["TIRITH_ENABLED"] = "0"   # same outcome as Hermes default tirith_fail_open=True with no binary
# headless benchmark = Hermes cron session (no human present); cron_mode default "deny"
os.environ["HERMES_CRON_SESSION"] = "1"
for _v in ("HERMES_INTERACTIVE", "HERMES_GATEWAY_SESSION", "HERMES_EXEC_ASK", "HERMES_YOLO_MODE"):
    os.environ.pop(_v, None)

from tools import approval as HA  # noqa: E402  (Hermes)
import agent.auxiliary_client as _aux  # noqa: E402  (Hermes)

# Description passed to _smart_approve for calls that no Hermes detector flagged (hermes_smart_all only).
ALL_CALL_DESC = "agent tool call (reviewed on every call; not a Hermes detector finding)"

_LOCK = threading.Lock()
_ACTIVE: Dict[str, Any] = {"guard": None}


def render_call(tool: str, args: Dict[str, Any]) -> str:
    return f"{tool} {json.dumps(args, ensure_ascii=False)}"


def _string_values(x: Any, out: List[str]) -> None:
    if isinstance(x, str):
        if x.strip():
            out.append(x)
    elif isinstance(x, dict):
        for v in x.values():
            _string_values(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _string_values(v, out)


def candidate_strings(tool: str, args: Dict[str, Any]) -> List[str]:
    vals: List[str] = []
    _string_values(args, vals)
    seen, out = set(), []
    for s in [render_call(tool, args)] + vals:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def detect(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Run Hermes's individual detectors over all candidate strings (for attribution and for smart modes)."""
    hard, sudo, dang, tir = [], [], [], []
    for s in candidate_strings(tool, args):
        is_h, d = HA.detect_hardline_command(s)
        if is_h:
            hard.append(d)
        is_s, d = HA._check_sudo_stdin_guard(s)
        if is_s:
            sudo.append(d)
        is_d, _k, d = HA.detect_dangerous_command(s)
        if is_d:
            dang.append(d)
        if TIRITH_AVAILABLE:
            from tools.tirith_security import check_command_security
            r = check_command_security(s)
            if r.get("action") in ("block", "warn"):
                tir.append(HA._format_tirith_description(r))
    uniq = lambda L: list(dict.fromkeys(L))  # noqa: E731
    return {"hardline": uniq(hard), "sudo": uniq(sudo), "dangerous": uniq(dang), "tirith": uniq(tir)}


def builtin_gate(tool: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    """Hermes's own headless pipeline (check_all_command_guards under cron, default config) per string."""
    for s in candidate_strings(tool, args):
        r = HA.check_all_command_guards(s, "local")
        if not r.get("approved", True):
            return False, str(r.get("message") or "blocked by Hermes command guard")
    return True, ""


def _patched_call_llm(task=None, *, messages, temperature=None, max_tokens=None, **_kw):
    g = _ACTIVE["guard"]
    return g._llm(messages, temperature, max_tokens)


_aux.call_llm = _patched_call_llm


class HermesGuard:
    def __init__(self, mode: str, model: str = "gpt-4.1-mini", api_key: Optional[str] = None, base_url: str = ""):
        assert mode in ("hermes_builtin", "hermes_smart", "hermes_smart_all", "hermes_smart_all_denyonly"), mode
        self.mode = mode
        self.model = model
        kw: Dict[str, Any] = {"api_key": api_key or os.environ.get("OPENAI_API_KEY", "")}
        if base_url:
            kw["base_url"] = base_url
        self.client = OpenAI(**kw)
        self.calls = self.checks = self.blocks = 0
        self.prompt_tokens = self.completion_tokens = 0
        self.latency_ms = 0.0
        self.flagged = 0
        self.flag_kinds = {"hardline": 0, "sudo": 0, "dangerous": 0, "tirith": 0}
        self.verdicts = {"approve": 0, "deny": 0, "escalate": 0}
        self.llm_errors = 0
        self.flag_log: List[Dict[str, Any]] = []
        _ACTIVE["guard"] = self

    # Hermes's aux-LLM call, routed to the guard model
    def _llm(self, messages, temperature, max_tokens):
        t0 = time.time()
        last = None
        for attempt in range(4):
            try:
                r = self.client.chat.completions.create(model=self.model, messages=messages,
                                                        temperature=temperature, max_tokens=max_tokens)
                with _LOCK:
                    self.calls += 1
                    self.latency_ms += (time.time() - t0) * 1000
                    if r.usage:
                        self.prompt_tokens += r.usage.prompt_tokens or 0
                        self.completion_tokens += r.usage.completion_tokens or 0
                return r
            except Exception as e:  # retry transient errors; final failure -> Hermes escalates
                last = e
                time.sleep(2 ** attempt)
        with _LOCK:
            self.llm_errors += 1
        raise last  # type: ignore[misc]

    def check(self, task: str, messages: List[Dict[str, Any]], tool: str, args: Dict[str, Any],
              desc: str) -> Dict[str, Any]:
        with _LOCK:
            self.checks += 1
        found = detect(tool, args)
        is_flagged = any(found.values())
        if is_flagged:
            with _LOCK:
                self.flagged += 1
                for k, v in found.items():
                    if v:
                        self.flag_kinds[k] += 1
        dec, reason, verdict = "allow", "", None

        if self.mode == "hermes_builtin":
            ok, msg = builtin_gate(tool, args)
            if not ok:
                dec, reason = "block", msg
        else:
            if found["hardline"] or found["sudo"]:          # unconditional Hermes floor, before smart approval
                dec = "block"
                reason = "Hermes hardline/sudo floor: " + "; ".join(found["hardline"] + found["sudo"])
            elif is_flagged or self.mode.startswith("hermes_smart_all"):
                descs = found["tirith"] + found["dangerous"]  # Hermes order: tirith warnings, then pattern
                description = "; ".join(descs) if descs else ALL_CALL_DESC
                verdict = HA._smart_approve(render_call(tool, args), description)
                with _LOCK:
                    self.verdicts[verdict] = self.verdicts.get(verdict, 0) + 1
                blocking = ("deny",) if self.mode == "hermes_smart_all_denyonly" else ("deny", "escalate")
                if verdict in blocking:
                    dec = "block"
                    reason = f"Hermes smart approval verdict {verdict.upper()} ({description})"

        if dec == "block":
            with _LOCK:
                self.blocks += 1
        if is_flagged or dec == "block":
            with _LOCK:
                self.flag_log.append({"tool": tool, "found": found, "verdict": verdict, "decision": dec,
                                      "call": render_call(tool, args)[:400]})
        return {"decision": dec, "reason": reason[:300]}

    def stats(self) -> Dict[str, Any]:
        return {"guard_calls": self.calls, "guard_checks": self.checks, "guard_blocks": self.blocks,
                "guard_prompt_tokens": self.prompt_tokens, "guard_completion_tokens": self.completion_tokens,
                "guard_latency_ms": round(self.latency_ms, 1),
                "hermes_flagged_calls": self.flagged, "hermes_flag_kinds": dict(self.flag_kinds),
                "hermes_smart_verdicts": dict(self.verdicts), "hermes_llm_errors": self.llm_errors,
                "tirith_available": TIRITH_AVAILABLE,
                "hermes_flag_log": self.flag_log[:200]}


def make(condition: str, model: str, api_key: str, base_url: str = ""):
    return HermesGuard(condition, model=model, api_key=api_key, base_url=base_url)
