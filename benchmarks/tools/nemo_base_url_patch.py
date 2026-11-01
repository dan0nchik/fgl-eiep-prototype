"""Make NeMo Guardrails (0.24.x) honour OPENAI_BASE_URL (e.g. the local Codex shim) for `engine: openai` models.

NeMo builds its OpenAI client from the config's model `parameters` and ignores OPENAI_BASE_URL, so we wrap
RailsConfig.from_path / from_content to inject `parameters.base_url` (and api_key) into every openai model.
Import this module once before any LLMRails is constructed. No-op when OPENAI_BASE_URL is unset.
"""
from __future__ import annotations

import os

from nemoguardrails import RailsConfig

_BASE = os.environ.get("OPENAI_BASE_URL", "")


def _inject(cfg):
    if not _BASE:
        return cfg
    for m in cfg.models:
        if (m.engine or "").lower() == "openai":
            p = dict(m.parameters or {})
            p.setdefault("base_url", _BASE)
            p.setdefault("api_key", os.environ.get("OPENAI_API_KEY", "local"))
            m.parameters = p
    return cfg


if _BASE and not getattr(RailsConfig, "_shim_patched", False):
    _fp = RailsConfig.from_path.__func__
    _fc = RailsConfig.from_content.__func__

    @classmethod
    def from_path(cls, *a, **k):
        return _inject(_fp(cls, *a, **k))

    @classmethod
    def from_content(cls, *a, **k):
        return _inject(_fc(cls, *a, **k))

    RailsConfig.from_path = from_path
    RailsConfig.from_content = from_content
    RailsConfig._shim_patched = True
