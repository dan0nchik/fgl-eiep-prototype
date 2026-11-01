"""NVIDIA NeMo Guardrails as a pre-action baseline guard for run_asb.py.

Uses the real `nemoguardrails` library (tested with 0.24.1), not a re-implementation:
  nemo_selfcheck : rails `self check input` + `self check output` with the library's shipped example prompts
                   (guards/nemo_configs/selfcheck, verbatim copy of nemoguardrails/examples/bots/abc/prompts.yml).
  nemo_safety    : rails `content safety check input/output $model=content_safety` with the official
                   NemoGuard (Aegis 23-category) prompts and output parsers (guards/nemo_configs/safety),
                   content-safety model = gpt-4.1-mini via OpenAI.

How a tool call is vetted (see NEMO_BASELINES.md for why):
  * input rail: LLMRails.check([{"role":"user","content":task}], rail_types=[RailType.INPUT]); computed once per
    task (cached). If it blocks, every tool call in that case is blocked.
  * output rail: the proposed tool call (name + args + tool description) is rendered as the assistant message and
    LLMRails.check([user task, assistant rendered-call], rail_types=[RailType.OUTPUT]) is run.
  NeMo 0.24.1's only shipped tool-call rail ("tool call validation", IORails rails.tool_output) is a model-free
  allowlist + JSON-schema check, not a safety judgment; the LLM safety rails act on text messages.

Errors: fail-open (allow), same as FGLMonitor; error count is reported in stats().

Also exports nemo_check_command(task, command, context="") for offline vetting of shell commands.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

CONFIG_DIR = Path(__file__).parent / "nemo_configs"
VARIANTS = {"nemo_selfcheck": "selfcheck", "nemo_safety": "safety"}


def render_tool_call(tool: str, args: Dict[str, Any], desc: str = "") -> str:
    a = json.dumps(args, ensure_ascii=False)[:1200]
    s = f"[The assistant calls the tool `{tool}` with arguments: {a}]"
    if desc:
        s += f"\n[Tool description: {desc[:500]}]"
    return s


_LOOP = None
_LOOP_LOCK = threading.Lock()


def _nemo_loop():
    """Process-wide asyncio loop thread for all NeMo calls (NeMo's OpenAI client state is shared across
    LLMRails instances and bound to the loop it was first used on)."""
    global _LOOP
    with _LOOP_LOCK:
        if _LOOP is None:
            import asyncio
            _LOOP = asyncio.new_event_loop()
            threading.Thread(target=_LOOP.run_forever, daemon=True, name="nemo-loop").start()
        return _LOOP


class NemoGuard:
    def __init__(self, variant: str = "selfcheck", model: str = "gpt-4.1-mini", api_key: Optional[str] = None,
                 base_url: str = "", enabled: bool = True):
        if api_key:
            os.environ.setdefault("OPENAI_API_KEY", api_key)
        if base_url:
            os.environ.setdefault("OPENAI_BASE_URL", base_url)
        self.variant = variant
        self.model = model
        self.enabled = enabled
        self.config_path = CONFIG_DIR / variant
        self._local = threading.local()
        self._lock = threading.Lock()
        self._build_lock = threading.Lock()
        # import (and parse the config) in the constructing thread: concurrent first imports from worker
        # threads deadlocked on the import lock in testing
        from nemoguardrails import LLMRails, RailsConfig  # noqa: F401
        from nemoguardrails.rails.llm.options import RailStatus, RailType  # noqa: F401
        RailsConfig.from_path(str(self.config_path))
        self._input_cache: Dict[str, Dict[str, Any]] = {}
        self._input_locks: Dict[str, threading.Lock] = {}
        # counters
        self.calls = 0            # LLM calls made by NeMo (from explain info)
        self.checks = 0           # tool calls vetted
        self.blocks = 0           # tool calls blocked
        self.input_checks = 0     # distinct tasks checked by the input rail
        self.input_blocks = 0     # tasks blocked by the input rail
        self.output_blocks = 0    # tool calls blocked by the output rail
        self.blocks_by_input = 0  # tool calls blocked because the task's input rail blocked
        self.errors = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.latency_ms = 0.0

    # All NeMo work runs on ONE process-wide asyncio loop thread (one LLMRails per guard); worker threads submit
    # coroutines to it. (One LLMRails per worker thread, each with its own loop via the sync check(), hung
    # indefinitely in testing with >2 threads: NeMo's async LLM client state is not loop-safe.)
    def _ensure_loop(self):
        with self._build_lock:
            if getattr(self, "_rails_obj", None) is None:
                import asyncio
                from nemoguardrails import LLMRails, RailsConfig
                loop = _nemo_loop()
                cfg = RailsConfig.from_path(str(self.config_path))
                for m in cfg.models:
                    m.model = self.model

                async def _build():
                    return LLMRails(cfg)
                self._rails_obj = asyncio.run_coroutine_threadsafe(_build(), loop).result(120)
        return _nemo_loop()

    async def _acheck(self, messages, rail: str):
        from nemoguardrails.rails.llm.options import RailType
        from nemoguardrails.context import explain_info_var
        from nemoguardrails.logging.explain import ExplainInfo
        info = ExplainInfo()
        explain_info_var.set(info)  # per-task context var: llm calls of THIS check only
        t0 = time.time()
        res = await self._rails_obj.check_async(
            messages, rail_types=[RailType.INPUT if rail == "input" else RailType.OUTPUT])
        return res, info, (time.time() - t0) * 1000

    def _run(self, messages: List[Dict[str, str]], rail: str) -> Dict[str, Any]:
        import asyncio
        from nemoguardrails.rails.llm.options import RailStatus
        loop = self._ensure_loop()
        res, info, dt = asyncio.run_coroutine_threadsafe(self._acheck(messages, rail), loop).result(180)
        n, pt, ct = 0, 0, 0
        llm_calls = []
        for c in (info.llm_calls if info is not None else []):
            n += 1
            pt += c.prompt_tokens or 0
            ct += c.completion_tokens or 0
            llm_calls.append({"task": c.task, "completion": (c.completion or "")[:200]})
        with self._lock:
            self.calls += n
            self.prompt_tokens += pt
            self.completion_tokens += ct
            self.latency_ms += dt
        return {"blocked": res.status == RailStatus.BLOCKED, "rail": res.rail, "llm_calls": llm_calls}

    def _input(self, task: str) -> Dict[str, Any]:
        with self._lock:
            if task in self._input_cache:
                return self._input_cache[task]
            lk = self._input_locks.setdefault(task, threading.Lock())
        with lk:
            with self._lock:
                if task in self._input_cache:
                    return self._input_cache[task]
            try:
                r = self._run([{"role": "user", "content": task}], "input")
                r["error"] = None
            except Exception as e:  # fail-open
                r = {"blocked": False, "rail": None, "error": f"{type(e).__name__}: {str(e)[:120]}"}
                with self._lock:
                    self.errors += 1
            with self._lock:
                self.input_checks += 1
                if r["blocked"]:
                    self.input_blocks += 1
                if r["error"] is None:  # do not cache errors; retry on next tool call
                    self._input_cache[task] = r
            return r

    def check_text(self, task: str, bot_text: str) -> Dict[str, Any]:
        """Input rail on task (cached) + output rail on bot_text. Fail-open."""
        if not self.enabled:
            return {"decision": "allow", "reason": "guard disabled"}
        with self._lock:
            self.checks += 1
        inp = self._input(task)
        if inp["blocked"]:
            with self._lock:
                self.blocks += 1
                self.blocks_by_input += 1
            return {"decision": "block", "reason": f"NeMo input rail '{inp['rail']}' blocked the user request.",
                    "stage": "input"}
        try:
            out = self._run([{"role": "user", "content": task}, {"role": "assistant", "content": bot_text}], "output")
        except Exception as e:
            with self._lock:
                self.errors += 1
            return {"decision": "allow", "reason": f"guard error (fail-open): {type(e).__name__}: {str(e)[:80]}",
                    "stage": "error"}
        if out["blocked"]:
            with self._lock:
                self.blocks += 1
                self.output_blocks += 1
            return {"decision": "block", "reason": f"NeMo output rail '{out['rail']}' blocked the proposed action.",
                    "stage": "output"}
        return {"decision": "allow", "reason": "passed NeMo input and output rails", "stage": "pass"}

    def check(self, task: str, messages: List[Dict[str, Any]], tool: str, args: Dict[str, Any],
              desc: str) -> Dict[str, Any]:
        r = self.check_text(task[:4000], render_tool_call(tool, args, desc))
        return {"decision": r["decision"], "reason": r["reason"]}

    def stats(self) -> Dict[str, Any]:
        return {"guard_calls": self.calls, "guard_checks": self.checks, "guard_blocks": self.blocks,
                "guard_prompt_tokens": self.prompt_tokens, "guard_completion_tokens": self.completion_tokens,
                "guard_latency_ms": round(self.latency_ms, 1),
                "nemo_variant": self.variant, "nemo_input_checks": self.input_checks,
                "nemo_input_blocks": self.input_blocks, "nemo_output_blocks": self.output_blocks,
                "nemo_blocks_by_input": self.blocks_by_input, "nemo_errors": self.errors}


def make(condition: str, model: str = "gpt-4.1-mini", api_key: str = "", base_url: str = ""):
    if condition not in VARIANTS:
        raise ValueError(f"unknown NeMo condition {condition}; choose from {sorted(VARIANTS)}")
    return NemoGuard(VARIANTS[condition], model=model, api_key=api_key, base_url=base_url)


_CMD_GUARDS: Dict[str, NemoGuard] = {}
_CMD_LOCK = threading.Lock()


def nemo_check_command(task: str, command: str, context: str = "", variant: str = "selfcheck",
                       model: str = "gpt-4.1-mini") -> Dict[str, Any]:
    """Vet a proposed shell command with NeMo rails (input rail on task, output rail on the rendered command).

    Returns {"decision": "allow"|"block", "reason": str, "stage": "input"|"output"|"pass"|"error"}.
    Fail-open on errors (stage == "error"). Needs OPENAI_API_KEY in the environment.
    """
    with _CMD_LOCK:
        g = _CMD_GUARDS.get(variant)
        if g is None:
            g = _CMD_GUARDS[variant] = NemoGuard(variant, model=model)
    bot = f"[The assistant runs the shell command: {command[:2000]}]"
    if context:
        bot += f"\n[Context: {context[:1500]}]"
    return g.check_text(task[:4000], bot)
