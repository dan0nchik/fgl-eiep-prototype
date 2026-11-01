"""Pluggable pre-action guards for run_asb.py.

Every guard exposes check(task, messages, tool, args, desc) -> {"decision": "allow"|"block", "reason": str}
and stats() -> dict. A guard family lives in its own module and exposes make(condition, model, api_key, base_url):
  none, fgl_monitor   -> fgl_guard.FGLMonitor (disabled / enabled)
  hermes_*            -> guards.hermes_guard.make
  nemo*               -> guards.nemo_guard.make
  fgl_abl_*           -> guards.fgl_ablation.make
"""
from __future__ import annotations

import importlib

FAMILIES = {"hermes_": "guards.hermes_guard", "nemo": "guards.nemo_guard", "fgl_abl_": "guards.fgl_ablation"}


def load_guard(condition: str, model: str, api_key: str, base_url: str = ""):
    if condition in ("none", "fgl_monitor"):
        from fgl_guard import FGLMonitor
        return FGLMonitor(model=model, api_key=api_key, base_url=base_url, enabled=(condition == "fgl_monitor"))
    for prefix, mod in FAMILIES.items():
        if condition.startswith(prefix):
            return importlib.import_module(mod).make(condition, model=model, api_key=api_key, base_url=base_url)
    raise ValueError(f"unknown condition {condition}")
