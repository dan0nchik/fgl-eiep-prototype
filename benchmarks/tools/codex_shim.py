"""Minimal local OpenAI-compatible /v1/chat/completions shim backed by the Codex CLI (`codex exec`).

Purpose: run LLM-based guards (NeMo rails, Hermes smart approval, FGL monitor, ...) through the owner's ChatGPT
subscription when no API credits are available. Text-only: no tools, no function calling, no images.

Each request: messages are flattened to one prompt ("[SYSTEM]/[USER]/[ASSISTANT]" blocks, preceded by a short
instruction to answer directly without running anything), then
    codex exec --skip-git-repo-check --ephemeral --ignore-user-config -s read-only -C <empty temp dir>
               -m <model> -o <tmpfile> -
is run with the prompt on stdin; the final agent message (from -o) is returned as choices[0].message.content.
`max_tokens`, `temperature`, `response_format` are NOT enforced by Codex (only passed as text hints; a JSON hint is
added when response_format=json_object). Usage counts are reported as 0.

Run:   python benchmarks/tools/codex_shim.py --port 8765 --model gpt-5.6-luna --parallel 8
Use:   OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="local")   model="gpt-5.6-luna"
Env:   CODEX_BIN (default: codex on PATH), CODEX_SHIM_EFFORT (optional model_reasoning_effort override)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREAMBLE = ("You are being used as a plain text-completion backend for an automated evaluation. Do NOT run any "
            "commands, do NOT read or write files, do NOT use any tools. Read the conversation below and reply "
            "with ONLY the next assistant message, exactly in the format the conversation asks for, with no "
            "preamble or commentary.\n\n")

STATE = {"model": "gpt-5.6-luna", "sem": threading.Semaphore(8), "calls": 0, "errors": 0, "lock": threading.Lock(),
         "timeout": 180}


def _content(c) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") in ("text", None))
    return "" if c is None else str(c)


def flatten(messages, response_format=None) -> str:
    parts = []
    for m in messages:
        parts.append(f"[{str(m.get('role', 'user')).upper()}]\n{_content(m.get('content'))}")
    s = PREAMBLE + "\n\n".join(parts) + "\n\n[ASSISTANT]\n"
    if isinstance(response_format, dict) and response_format.get("type") in ("json_object", "json_schema"):
        s = s.replace("[ASSISTANT]\n", "(Reply with a single valid JSON object only.)\n[ASSISTANT]\n")
    return s


def run_codex(prompt: str, model: str) -> str:
    codex = os.environ.get("CODEX_BIN") or shutil.which("codex") or "/opt/homebrew/bin/codex"
    work = tempfile.mkdtemp(prefix="codex_shim_")
    out = os.path.join(work, "last.txt")
    cmd = [codex, "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-user-config", "-s", "read-only",
           "-C", work, "-m", model, "--color", "never", "-o", out]
    eff = os.environ.get("CODEX_SHIM_EFFORT")
    if eff:
        cmd += ["-c", f'model_reasoning_effort="{eff}"']
    cmd.append("-")
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=STATE["timeout"], cwd=work)
        if os.path.exists(out):
            txt = open(out).read().strip()
            if txt or p.returncode == 0:
                return txt
        raise RuntimeError(f"codex exit {p.returncode}: {(p.stderr or '')[-300:]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, obj=None, raw=None, ctype="application/json"):
        b = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self._send(200, {"object": "list", "data": [{"id": STATE["model"], "object": "model",
                                                                 "owned_by": "codex-shim"}]})
        return self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._send(404, {"error": {"message": "only /v1/chat/completions is supported"}})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except Exception:
            return self._send(400, {"error": {"message": "bad json"}})
        model = STATE["model"]  # one model for every caller (comparability); requested name is ignored
        prompt = flatten(req.get("messages", []), req.get("response_format"))
        try:
            last = None
            for attempt in range(4):          # transient Codex/subscription failures: back off and retry
                try:
                    with STATE["sem"]:
                        txt = run_codex(prompt, model)
                    break
                except Exception as e:
                    last = e
                    print(f"codex attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[-200:]}", flush=True)
                    time.sleep(15 * (attempt + 1))
            else:
                raise last
            with STATE["lock"]:
                STATE["calls"] += 1
        except Exception as e:
            with STATE["lock"]:
                STATE["errors"] += 1
            return self._send(502, {"error": {"message": f"codex shim error: {type(e).__name__}: {str(e)[:300]}",
                                              "type": "server_error"}})
        cid = "chatcmpl-" + uuid.uuid4().hex[:24]
        now = int(time.time())
        if req.get("stream"):
            chunks = [{"id": cid, "object": "chat.completion.chunk", "created": now, "model": model,
                       "choices": [{"index": 0, "delta": {"role": "assistant", "content": txt}, "finish_reason": None}]},
                      {"id": cid, "object": "chat.completion.chunk", "created": now, "model": model,
                       "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]
            body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
            return self._send(200, raw=body.encode(), ctype="text/event-stream")
        return self._send(200, {"id": cid, "object": "chat.completion", "created": now, "model": model,
                                "choices": [{"index": 0, "message": {"role": "assistant", "content": txt},
                                             "finish_reason": "stop"}],
                                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--model", default="gpt-5.6-luna")
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()
    STATE["model"] = a.model
    STATE["sem"] = threading.Semaphore(a.parallel)
    STATE["timeout"] = a.timeout
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print(f"codex shim on http://{a.host}:{a.port}/v1 model={a.model} parallel={a.parallel}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
