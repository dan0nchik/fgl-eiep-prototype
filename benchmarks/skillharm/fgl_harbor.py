#!/usr/bin/env python3
"""Harbor launcher used for EVERY SkillHarm trial in our runs (none and defense conditions alike).

Why: the victim is Codex on a ChatGPT-subscription login (no API credits). Harbor's codex agent writes an
API-key auth.json; we instead bind-mount the owner's ChatGPT auth.json READ-ONLY into the container and point
$CODEX_HOME/auth.json at it. Nothing else changes.

  fgl_harbor.py [--authors-launcher PATH] run ...harbor args...

--authors-launcher: load the authors' defense launcher (victim_eval/eval/harbor_run.py or eval_defense/harbor_run.py)
unchanged and apply ITS exec_as_agent patch (AGENTS.md defense injection for codex) on top of ours, so the
defense channel is byte-identical to the authors'. Env: CODEX_SUB_AUTH (host auth.json path),
SKILLHARM_DEFENSE_PROMPT_FILE (read by the authors' launcher), CODEX_PROXY_FILE (proxy URL file;
injected only into the `codex exec` call's env, never into setup commands), FGL_AGENT_SETUP_TIMEOUT_MULT (default 2)."""
import importlib.util, json, os, re, sys

AUTH_HOST = os.path.expanduser(os.environ.get("CODEX_SUB_AUTH", "~/.codex_sub/auth.json"))
AUTH_CT = "/opt/codex-auth/auth.json"
_pf = os.path.expanduser(os.environ.get("CODEX_PROXY_FILE", ""))
PROXY = open(_pf).read().strip() if _pf and os.path.isfile(_pf) else ""
NO_PROXY = "localhost,127.0.0.1,::1,host.docker.internal"
SETUP_MULT = os.environ.get("FGL_AGENT_SETUP_TIMEOUT_MULT", "2")
HARBOR_AUTH_BLOCK = re.compile(
    r'cat >/tmp/codex-secrets/auth\.json <<EOF\n\{\n  "OPENAI_API_KEY": "\$\{OPENAI_API_KEY\}"\n\}\nEOF\n'
    r'ln -sf /tmp/codex-secrets/auth\.json "\$CODEX_HOME/auth\.json"\n')

def patch_auth():
    from harbor.agents.installed.base import BaseInstalledAgent
    orig = BaseInstalledAgent.exec_as_agent
    async def patched(self, environment, command, env=None, cwd=None, timeout_sec=None):
        if HARBOR_AUTH_BLOCK.search(command):
            command = HARBOR_AUTH_BLOCK.sub(f'ln -sf {AUTH_CT} "$CODEX_HOME/auth.json"\n', command)
        if env:
            env = {k: v for k, v in env.items() if k not in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL")}
        if "codex exec " in command and PROXY:
            # proxy only for the Codex model traffic; agent setup (apt/npm/nvm) goes direct
            env = dict(env or {}); env.update({k: PROXY for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")})
            env.update({k: NO_PROXY for k in ("NO_PROXY", "no_proxy")})
        return await orig(self, environment, command, env=env, cwd=cwd, timeout_sec=timeout_sec)
    BaseInstalledAgent.exec_as_agent = patched

def main():
    args = sys.argv[1:]
    authors = None
    if args[:1] == ["--authors-launcher"]:
        authors, args = args[1], args[2:]
    if not os.path.isfile(AUTH_HOST):
        sys.exit(f"auth file missing: {AUTH_HOST}")
    if args[:1] == ["run"]:
        args += ["--agent-setup-timeout-multiplier", SETUP_MULT,
                 "--environment-build-timeout-multiplier", SETUP_MULT]
        args += ["--mounts-json", json.dumps([{"type": "bind", "source": AUTH_HOST, "target": AUTH_CT, "read_only": True}])]
    patch_auth()
    if authors:
        spec = importlib.util.spec_from_file_location("authors_harbor_run", authors)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        mod._ensure_harbor_supported()
        mod._patch_exec_as_agent(mod._read_defense_text())   # wraps our patched method
    sys.argv = ["harbor"] + args
    from harbor.cli.main import app
    return app()

if __name__ == "__main__":
    sys.exit(main())
