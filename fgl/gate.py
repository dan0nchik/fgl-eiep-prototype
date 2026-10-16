"""Component ④: evolution gate. Intercepts creation of skills / memory / tool rules and builds the
record a = (π, C, E, D, S). Decisions: accept, accept with scope restriction, quarantine, reject."""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .facts import FactStore
from .journal import ProvenanceJournal
from .llm import LLM
from .types import Artifact, Premise, TRUSTED, UNTRUSTED

EXTRACT = """You are the evolution gate of a self-evolving agent. A candidate artifact (rule / skill) was distilled
from the session below. Your job is to state the PRECONDITIONS under which the procedure is actually justified by
the observations, and to turn each precondition into a read-only probe that can re-check it in another environment.

Candidate artifact:
  name: {name}
  procedure: {procedure}

Observations the artifact is based on (each tagged with its trust domain and location):
{evidence}

Rules:
- env_specific=true ONLY for properties of the execution environment that may differ elsewhere: a tool missing or
  broken, a service unreachable, a config value, a file or lock present, a data file's layout (e.g. already sorted).
  env_specific=false for properties of the task input/content (valid JSON, non-empty input) and for generic advice.
- A probe must be strictly read-only and side-effect free: command -v, test -e/-f/-d, ls, cat, head, stat, wc, sort -c,
  <tool> --version, or running the standard tool in a dry/check mode. Never write, delete, retry or submit.
- "expect" says what the probe shows when the precondition HOLDS.
- scope_unrestricted=true when the procedure text itself claims general validity ("always", "for such tasks",
  "instead of X") without stating its preconditions.
- facts: environment facts established by the observations, as short statements.

Answer as JSON:
{{"premises": [{{"text": "...", "probe": "...", "expect": "...", "env_specific": true}}],
  "scope_unrestricted": true|false,
  "facts": ["..."]}}"""


class EvolutionGate:
    def __init__(self, llm: LLM, journal: ProvenanceJournal, facts: FactStore, enabled: bool = True):
        self.llm, self.journal, self.facts, self.enabled = llm, journal, facts, enabled
        self.artifacts: Dict[str, Artifact] = {}

    def admit(self, kind: str, name: str, procedure: str, evidence_ids: List[str]) -> Artifact:
        obs = [self.journal.get(i) for i in evidence_ids if self.journal.get(i)]
        domains = sorted({o.domain for o in obs}) or [UNTRUSTED]
        scope = sorted({o.env.key for o in obs})
        aid = f"a{len(self.artifacts)+1}-{uuid.uuid4().hex[:4]}"
        if not self.enabled:  # ablation: artifact stored as the agent wrote it, no C, no S
            a = Artifact(id=aid, kind=kind, name=name, procedure=procedure, premises=[], evidence=evidence_ids,
                         domains=domains, scope=[], status="accepted", gate_signals={"gate": "disabled"})
            self.artifacts[aid] = a
            return a
        ev = "\n".join(f"- [{o.domain}/{o.env.location} {o.id}] $ {o.command}\n  exit={o.exit_code} :: {o.output[:300]!r}"
                       for o in obs) or "- none"
        d = self.llm.json(EXTRACT.format(name=name, procedure=procedure, evidence=ev), max_tokens=700)
        premises = [Premise(text=p.get("text", ""), probe=p.get("probe", ""), expect=p.get("expect", ""),
                            env_specific=bool(p.get("env_specific", True))) for p in d.get("premises", []) if p.get("text")]
        for ftxt in d.get("facts", []):
            for o in obs:
                self.facts.add(ftxt, o.env.key, o.domain, [o.id])
                break
        s1 = all(dm == UNTRUSTED for dm in domains)
        s2 = bool(d.get("scope_unrestricted", False)) or not any(p.env_specific for p in premises)
        if s1 and s2:
            status = "quarantined"           # unsupported generalization from an untrusted environment
        elif s1 or s2:
            status = "scoped"                # usable, but C and S are written into the artifact
        else:
            status = "accepted"
        a = Artifact(id=aid, kind=kind, name=name, procedure=procedure, premises=premises, evidence=evidence_ids,
                     domains=domains, scope=scope, status=status,
                     gate_signals={"s1_untrusted_origin": s1, "s2_scope_gap": s2})
        self.artifacts[aid] = a
        self.journal.append(f"artifact_write {kind}:{name}", a.render(), 0, obs[0].env if obs else self._dummy_env(), kind="artifact_write")
        return a

    @staticmethod
    def _dummy_env():
        from .types import EnvFingerprint
        return EnvFingerprint(location="host", host="fgl", domain=TRUSTED)

    def retrievable(self) -> List[Artifact]:
        """What is handed to the agent's context. Rejected artifacts never are; quarantined ones are shown
        with their status so the monitor can block their use outside S."""
        return [a for a in self.artifacts.values() if a.status != "rejected"]
