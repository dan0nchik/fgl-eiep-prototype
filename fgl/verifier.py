"""Component ⑥: premise verifier. Re-grounds an artifact's preconditions in the TARGET environment with
read-only probes, and records the result as a new observation and fact."""
from __future__ import annotations

import re
from typing import Tuple

from .facts import FactStore
from .journal import ProvenanceJournal
from .llm import LLM
from .sensor import ExecutionContextSensor, Target
from .types import Premise

READ_ONLY = {"command", "which", "type", "test", "[", "ls", "cat", "head", "tail", "stat", "wc", "file", "grep", "find",
             "du", "df", "id", "env", "printenv", "echo", "uname", "pwd", "readlink", "realpath", "true", "uniq", "diff",
             "cmp", "md5sum", "sha256sum", "shasum", "awk", "cut", "tr"}
FLAG_ONLY = re.compile(r"(--version|--help|-V\b|--dry-run|--check|\s-n\b|\s-h\b)")
DENY = re.compile(r"(>\s*[^&]|>>|\brm\b|\bmv\b|\bcp\b|\btouch\b|\bmkdir\b|\bchmod\b|\bchown\b|\bkill\b|\bsubmit\b|"
                  r"\bprocess\b|\bcurl\b|\bwget\b|\bpip\b|\bapt\b|\bsed -i\b|\btee\b|\bdd\b)")

JUDGE = """A precondition of a learned rule is being re-checked in a new environment.
Precondition: "{premise}"
Probe command: $ {probe}
Expected when the precondition holds: {expect}
Probe exit code: {rc}
Probe output:
{out}

Does the precondition HOLD in this environment? Answer as JSON: {{"verdict": "confirmed|refuted|unknown", "why": "..."}}"""


class PremiseVerifier:
    def __init__(self, llm: LLM, sensor: ExecutionContextSensor, journal: ProvenanceJournal, facts: FactStore,
                 enabled: bool = True):
        self.llm, self.sensor, self.journal, self.facts, self.enabled = llm, sensor, journal, facts, enabled
        self.probes_run = 0

    @staticmethod
    def safe(probe: str) -> bool:
        """Read-only fence: every pipeline segment must start with a read-only tool or be a flag-only invocation."""
        p = probe.strip()
        if not p or DENY.search(p) or ">" in p.replace(">/dev/null", "").replace("2>&1", ""):
            return False
        for seg in re.split(r"\|\||&&|\||;", p):
            seg = seg.strip()
            if not seg:
                continue
            tok = seg.split()
            head = tok[0]
            if head in READ_ONLY or (head == "sort" and ("-c" in tok or "--check" in tok)):
                continue
            if head in ("python3", "python") and len(tok) > 1 and tok[1] in ("-c", "-m") and ("import" in seg or "json.tool" in seg or FLAG_ONLY.search(seg)):
                continue
            if head in ("make", "sh") and "-n" in tok:
                continue
            if FLAG_ONLY.search(seg):
                continue
            return False
        return True

    def verify(self, premise: Premise, target: Target) -> Tuple[str, str]:
        """Returns (verdict, observation_id). verdict in confirmed | refuted | unknown."""
        if not self.enabled or not self.safe(premise.probe):
            return "unknown", ""
        fp = self.sensor.fingerprint(target)
        rc, out = self.sensor.run(target, premise.probe)
        self.probes_run += 1
        o = self.journal.append(premise.probe, out, rc, fp, kind="probe")
        d = self.llm.json(JUDGE.format(premise=premise.text, probe=premise.probe, expect=premise.expect, rc=rc,
                                       out=out[:800]), max_tokens=120)
        v = d.get("verdict", "unknown")
        if v in ("confirmed", "refuted"):
            self.facts.add(premise.text, fp.key, fp.domain, [o.id], status=v)
        return v, o.id
