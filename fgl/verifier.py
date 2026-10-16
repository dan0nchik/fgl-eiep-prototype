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

ALLOW = re.compile(r"^\s*(command -v|which|test |\[ |ls\b|cat\b|head\b|tail\b|stat\b|wc\b|sort -c|sort --check|file\b|"
                   r"grep\b|find\b|du\b|df\b|id\b|env\b|printenv\b|echo\b|uname\b|pwd\b|readlink\b|realpath\b|"
                   r"[A-Za-z0-9_./-]+ (--version|-V|--help|--dry-run|--check|-n)\b|make -n\b|python3? -c\b|sh -n\b|true\b)")
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
        p = probe.strip()
        return bool(p) and bool(ALLOW.match(p)) and not DENY.search(p) and "|" not in p.split("||")[0].replace("||", "")

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
