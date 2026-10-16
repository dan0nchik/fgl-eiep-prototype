"""Component ①: execution-context sensor. Runs commands on the host or inside a Docker container and
stamps every result with an environment fingerprint computed by the harness (never by the agent)."""
from __future__ import annotations

import hashlib
import os
import platform
import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .types import EnvFingerprint, TRUSTED, UNTRUSTED

# Hard safety fence for agent-generated host commands in the prototype: the workspace is a temp dir;
# anything that escapes it or touches privileges / network is refused by the harness itself.
FORBIDDEN = [r"\bsudo\b", r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+/(\s|$)", r"\bmkfs\b", r"\bdd\s+if=", r"\bcurl\b", r"\bwget\b",
             r"\bssh\b", r"\bscp\b", r"\bchmod\s+-R\s+777\s+/", r"/etc/", r"~/\.", r"\$HOME", r"\bnc\b", r"\bpython3?\s+-m\s+http"]


class Target:
    """Where a command executes. Exactly one of host workspace or container."""

    def __init__(self, name: str, location: str, workdir: str, container_id: str = "",
                 domain: str = TRUSTED, config_files: Optional[List[str]] = None, tools: Optional[List[str]] = None):
        self.name = name
        self.location = location            # host | container
        self.workdir = workdir
        self.container_id = container_id
        self.domain = domain
        self.config_files = config_files or []
        self.tools = tools or []
        self._fp: Optional[EnvFingerprint] = None


class ExecutionContextSensor:
    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    # ---- raw execution -------------------------------------------------------------------
    def _run_host(self, cmd: str, workdir: str) -> Tuple[int, str]:
        for pat in FORBIDDEN:
            if re.search(pat, cmd):
                return 126, f"harness: command refused by safety fence ({pat})"
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": workdir, "LANG": "C.UTF-8"}
        try:
            p = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True,
                               timeout=self.timeout, env=env)
            return p.returncode, (p.stdout + p.stderr)[-4000:]
        except subprocess.TimeoutExpired:
            return 124, "harness: timeout"

    def _run_container(self, cmd: str, container_id: str, workdir: str) -> Tuple[int, str]:
        try:
            p = subprocess.run(["docker", "exec", "-w", workdir, container_id, "sh", "-c", cmd],
                               capture_output=True, text=True, timeout=self.timeout)
            return p.returncode, (p.stdout + p.stderr)[-4000:]
        except subprocess.TimeoutExpired:
            return 124, "harness: timeout"

    def run(self, target: Target, cmd: str) -> Tuple[int, str]:
        if target.location == "container":
            return self._run_container(cmd, target.container_id, target.workdir)
        return self._run_host(cmd, target.workdir)

    # ---- fingerprint ---------------------------------------------------------------------
    def fingerprint(self, target: Target, refresh: bool = False) -> EnvFingerprint:
        if target._fp is not None and not refresh:
            return target._fp
        if target.location == "container":
            insp = subprocess.run(["docker", "inspect", "-f", "{{.Image}}|{{.Config.User}}", target.container_id],
                                  capture_output=True, text=True).stdout.strip()
            image, user = (insp.split("|") + [""])[:2]
            _, kernel = self._run_container("uname -sr", target.container_id, target.workdir)
            host = "docker"
        else:
            image, user, kernel, host = "", os.environ.get("USER", ""), platform.platform(), platform.node()
        cfg = hashlib.sha256()
        for f in target.config_files:
            rc, out = self.run(target, f"cat {shlex.quote(f)} 2>/dev/null")
            cfg.update(f.encode() + out.encode())
        tool_hashes: Dict[str, str] = {}
        for t in target.tools:
            rc, out = self.run(target, f"p=$(command -v {shlex.quote(t)} 2>/dev/null); [ -n \"$p\" ] && (sha256sum \"$p\" 2>/dev/null || shasum -a 256 \"$p\") | cut -c1-16 || echo missing")
            tool_hashes[t] = out.strip().split()[0] if out.strip() else "missing"
        target._fp = EnvFingerprint(location=target.location, host=host, container_id=target.container_id[:12],
                                    image_digest=image.replace("sha256:", ""), cwd=target.workdir, user=user or "root",
                                    kernel=kernel.strip(), config_hash=cfg.hexdigest(), tool_hashes=tool_hashes,
                                    network="none" if target.location == "container" else "host",
                                    domain=target.domain)
        return target._fp
