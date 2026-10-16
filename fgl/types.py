"""Data model of the Factual Grounding Layer (FGL Plan v3, section 7)."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

TRUSTED, UNTRUSTED = "T", "U"


@dataclass(frozen=True)
class EnvFingerprint:
    """Component ①: facts about the execution place, produced by the harness, never by the agent."""
    location: str                 # "host" | "container"
    host: str
    container_id: str = ""
    image_digest: str = ""
    cwd: str = ""
    user: str = ""
    kernel: str = ""
    config_hash: str = ""         # hash of relevant config files in the workspace
    tool_hashes: Dict[str, str] = field(default_factory=dict)
    network: str = ""
    domain: str = TRUSTED         # T | U, assigned by the harness

    @property
    def key(self) -> str:
        return f"{self.location}:{self.container_id or self.host}:{self.image_digest[:12]}:{self.config_hash[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Observation:
    """Component ②: one journal record."""
    id: str
    command: str
    output: str
    exit_code: int
    env: EnvFingerprint
    domain: str
    ts: float
    kind: str = "exec"            # exec | probe | artifact_write | retrieve
    prev_hash: str = ""
    hash: str = ""

    def compute_hash(self) -> str:
        body = json.dumps({"id": self.id, "command": self.command, "output": self.output,
                           "exit_code": self.exit_code, "env": self.env.to_dict(), "domain": self.domain,
                           "ts": self.ts, "kind": self.kind, "prev": self.prev_hash}, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()


@dataclass
class Fact:
    """Component ③: structured statement with scope, validity and evidence."""
    id: str
    text: str
    scope_key: str                # EnvFingerprint.key where established
    domain: str
    observation_ids: List[str]
    status: str = "confirmed"     # confirmed | refuted
    expires_at: Optional[float] = None

    def valid(self) -> bool:
        return self.expires_at is None or self.expires_at > time.time()


@dataclass
class Premise:
    """One applicability precondition C_i of an artifact, with a read-only probe to re-ground it."""
    text: str
    probe: str = ""               # read-only shell probe, must pass PremiseVerifier.allowlist
    expect: str = ""              # what the probe output should show if the premise holds
    env_specific: bool = True     # does it restrict the environment (False = generic statement)


@dataclass
class Artifact:
    """Component ④: evolution record a = (π, C, E, D, S)."""
    id: str
    kind: str                     # skill | memory | tool_rule
    name: str
    procedure: str                # π
    premises: List[Premise]       # C
    evidence: List[str]           # E: observation ids
    domains: List[str]            # D: trust domains of E
    scope: List[str]              # S: fingerprint keys where confirmed
    status: str = "accepted"      # accepted | scoped | quarantined | rejected
    gate_signals: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def render(self) -> str:
        c = "; ".join(p.text for p in self.premises) or "none recorded"
        tag = "" if self.status == "accepted" else f" [{self.status}]"
        return f"[{self.kind} {self.name}{tag}]\nProcedure: {self.procedure}\nApplies when: {c}\nConfirmed in: {', '.join(self.scope) or 'nowhere'}"


@dataclass
class Signals:
    s1_untrusted_origin: bool = False
    s2_scope_gap: bool = False
    s3_boundary_crossing: bool = False
    s4_unverified_premises: bool = False
    s5_deviation: bool = False
    s6_generalization: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def eiep(self) -> bool:
        return (self.s1_untrusted_origin or self.s2_scope_gap) and self.s3_boundary_crossing and self.s4_unverified_premises

    @property
    def risk(self) -> float:
        w = {"s1_untrusted_origin": 0.2, "s2_scope_gap": 0.2, "s3_boundary_crossing": 0.2,
             "s4_unverified_premises": 0.25, "s5_deviation": 0.1, "s6_generalization": 0.05}
        return round(sum(v for k, v in w.items() if getattr(self, k)), 3)

    def to_dict(self) -> Dict[str, Any]:
        d = {k: getattr(self, k) for k in ("s1_untrusted_origin", "s2_scope_gap", "s3_boundary_crossing",
                                           "s4_unverified_premises", "s5_deviation", "s6_generalization")}
        d.update({"eiep": self.eiep, "risk": self.risk, "details": self.details})
        return d


@dataclass
class Decision:
    action: str                   # allow | allow_audit | substitute | block
    reason: str
    signals: Optional[Signals] = None
    artifacts: List[str] = field(default_factory=list)
    probes: int = 0
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "reason": self.reason, "artifacts": self.artifacts, "probes": self.probes,
                "latency_ms": round(self.latency_ms, 1), "signals": self.signals.to_dict() if self.signals else None}
