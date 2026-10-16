"""Thin JSON-mode wrapper over an OpenAI-compatible client with token and latency accounting."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI


class LLM:
    def __init__(self, model: str = "gpt-4.1-mini", api_key: Optional[str] = None, base_url: str = ""):
        kw: Dict[str, Any] = {"api_key": api_key or os.environ.get("OPENAI_API_KEY", "")}
        if base_url:
            kw["base_url"] = base_url
        self.client = OpenAI(**kw)
        self.model = model
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.latency_ms = 0.0

    def _account(self, resp, t0):
        self.calls += 1
        self.latency_ms += (time.time() - t0) * 1000
        if resp.usage:
            self.prompt_tokens += resp.usage.prompt_tokens or 0
            self.completion_tokens += resp.usage.completion_tokens or 0

    def json(self, prompt: str, max_tokens: int = 600, system: str = "") -> Dict[str, Any]:
        msgs: List[Dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        t0 = time.time()
        resp = self.client.chat.completions.create(model=self.model, messages=msgs, temperature=0.0,
                                                   max_tokens=max_tokens,
                                                   response_format={"type": "json_object"})
        self._account(resp, t0)
        txt = resp.choices[0].message.content or "{}"
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", txt, re.S)
            return json.loads(m.group(0)) if m else {}

    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None,
             max_tokens: int = 700):
        t0 = time.time()
        kw: Dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0.0, "max_tokens": max_tokens}
        if tools:
            kw["tools"] = tools
            kw["tool_choice"] = "auto"
        resp = self.client.chat.completions.create(**kw)
        self._account(resp, t0)
        return resp.choices[0].message

    def stats(self) -> Dict[str, Any]:
        return {"calls": self.calls, "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens, "latency_ms": round(self.latency_ms, 1)}
