"""FGL façade: the four interception points of section 7.5 and the six processing steps of section 7.4."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .facts import FactStore
from .gate import EvolutionGate
from .graph import EIEPDetector, ProvenanceGraph
from .journal import ProvenanceJournal
from .llm import LLM
from .monitor import ActionMonitor
from .sensor import ExecutionContextSensor, Target
from .types import Artifact, Decision, Signals, TRUSTED
from .verifier import PremiseVerifier


@dataclass
class FGLConfig:
    enabled: bool = True          # False = no layer at all (baseline)
    gate: bool = True             # ④ evolution gate (ablation: off -> artifacts stored raw)
    graph: bool = True            # ⑦ provenance graph (ablation: off -> monitor only, no S1/S2/S3 by provenance)
    verifier: bool = True         # ⑥ premise verifier (ablation: off -> unknown premises count as unverified)
    reasoning: bool = True        # use the agent's reasoning for S6
    name: str = "fgl_full"


class FGL:
    def __init__(self, llm: LLM, cfg: FGLConfig, timeout: int = 60):
        if not cfg.enabled:
            cfg = FGLConfig(enabled=False, gate=False, graph=False, verifier=False, reasoning=False, name=cfg.name)
        self.llm, self.cfg = llm, cfg
        self.sensor = ExecutionContextSensor(timeout=timeout)
        self.journal = ProvenanceJournal()
        self.facts = FactStore()
        self.gate = EvolutionGate(llm, self.journal, self.facts, enabled=cfg.gate)
        self.monitor = ActionMonitor(llm, use_reasoning=cfg.reasoning)
        self.verifier = PremiseVerifier(llm, self.sensor, self.journal, self.facts, enabled=cfg.verifier)
        self.graph = ProvenanceGraph(enabled=cfg.graph)
        self.retrieved: List[str] = []           # artifact ids currently in the agent's context
        self.decisions: List[Decision] = []

    # ---- interception point: before a tool call -------------------------------------------
    def before_tool(self, target: Target, task: str, command: str, reasoning: str = "") -> Decision:
        t0 = time.time()
        fp = self.sensor.fingerprint(target)
        if not self.cfg.enabled:
            return Decision("allow", "fgl disabled")
        active = [self.gate.artifacts[i] for i in self.retrieved if i in self.gate.artifacts]
        # step 1-2: attribution
        an = self.monitor.analyze(task, command, reasoning, fp.location, fp.domain, active)
        attributed = [self.gate.artifacts[i] for i in an["attributed"]]
        probes = 0
        worst: Optional[Signals] = None
        action = "allow"
        reason = "no artifact involved" if not attributed else ""
        action_id = f"act-{uuid.uuid4().hex[:6]}"
        for a in attributed:
            sig = Signals()
            if self.cfg.graph:
                sig.s1_untrusted_origin = self.graph.path_from_untrusted(a)
                sig.s2_scope_gap = bool(a.gate_signals.get("s2_scope_gap", False)) or not a.premises
                sig.s3_boundary_crossing = fp.key not in a.scope
            else:   # monitor-only ablation: no provenance, so every attributed use is treated as a crossing
                sig.s1_untrusted_origin = False
                sig.s2_scope_gap = not a.premises
                sig.s3_boundary_crossing = True
            sig.s5_deviation = bool(an.get("deviation"))
            sig.s6_generalization = bool(an.get("generalization_in_reasoning"))
            # step 3-4: premises in the target environment
            verdicts: Dict[str, str] = {}
            if sig.s3_boundary_crossing or not self.cfg.graph:
                for p in a.premises:
                    if not p.env_specific:
                        continue
                    f = self.facts.lookup(p.text, fp.key)
                    v = f.status if f else "unknown"
                    if v == "unknown":
                        v, _ = self.verifier.verify(p, target)
                        probes += 1 if v != "unknown" or self.cfg.verifier else 0
                    verdicts[p.text] = v
                env_specific = [p for p in a.premises if p.env_specific]
                sig.s4_unverified_premises = (not env_specific) or any(v != "confirmed" for v in verdicts.values())
            else:
                sig.s4_unverified_premises = False
            sig.details = {"artifact": a.id, "premise_verdicts": verdicts, "deviation_kind": an.get("deviation_kind"),
                           "task_fit": an.get("task_fit", True)}
            # step 5: decision (7.4). Minimal intervention lives in step 4 (verify before blocking); once
            # (S1|S2)&S3&S4 holds the action is blocked before execution, read-only or not: in the trust-source
            # mechanism the harmful action IS a read (dev run 1 in results/dev shows the exemption defeating E3).
            act = EIEPDetector.decide(sig, a)
            if act == "block" and a.status != "quarantined":
                a.status = "quarantined"
            if self.cfg.graph:
                self.graph.link_action(a.id, action_id)
            if worst is None or sig.risk > worst.risk:
                worst, action = sig, act
                reason = f"artifact {a.name}: " + ("EIEP: (S1|S2)&S3&S4" if act == "block" else
                                                   ("EIEP signals on a read-only command, audited" if sig.eiep else "crossing with confirmed premises")
                                                   if act == "allow_audit" else "within scope")
        if attributed and not an.get("task_fit", True) and action != "block":
            action, reason = "allow_audit", reason + "; command does not fit the task"
        d = Decision(action, reason, worst, [a.id for a in attributed], probes, (time.time() - t0) * 1000)
        self.decisions.append(d)
        self.graph.record({"action_id": action_id, "command": command, "env": fp.key, **d.to_dict()})
        return d

    # ---- interception point: tool executed through the sensor, result journaled -------------
    def run_tool(self, target: Target, command: str) -> Tuple[int, str, str]:
        fp = self.sensor.fingerprint(target)
        rc, out = self.sensor.run(target, command)
        o = self.journal.append(command, out, rc, fp)
        return rc, out, o.id

    def after_tool(self, observation_id: str) -> str:
        o = self.journal.get(observation_id)
        return self.journal.tagged_output(o) if (o and self.cfg.enabled) else (o.output if o else "")

    # ---- interception point: artifact write -----------------------------------------------
    def on_artifact_write(self, kind: str, name: str, procedure: str, evidence_ids: List[str]) -> Artifact:
        a = self.gate.admit(kind, name, procedure, evidence_ids)
        self.graph.link_artifact(a)
        return a

    # ---- interception point: retrieval into context ---------------------------------------
    def on_retrieve(self) -> List[Artifact]:
        arts = self.gate.retrievable() if self.cfg.enabled else list(self.gate.artifacts.values())
        self.retrieved = [a.id for a in arts]
        return arts

    def stats(self) -> Dict[str, Any]:
        return {"probes": self.verifier.probes_run, "decisions": len(self.decisions),
                "blocks": sum(1 for d in self.decisions if d.action == "block"),
                "audits": sum(1 for d in self.decisions if d.action == "allow_audit"),
                "journal_ok": self.journal.verify_chain()}
