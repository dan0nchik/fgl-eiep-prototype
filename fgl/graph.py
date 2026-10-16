"""Component ⑦: provenance graph (observation -> artifact -> action) and the EIEP detector."""
from __future__ import annotations

from typing import Any, Dict, List

from .types import Artifact, Signals


class ProvenanceGraph:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.edges: List[Dict[str, str]] = []       # {"src","dst","kind"}
        self.audit: List[Dict[str, Any]] = []

    def link_artifact(self, a: Artifact):
        for oid in a.evidence:
            self.edges.append({"src": oid, "dst": a.id, "kind": "observation->artifact"})

    def link_action(self, a_id: str, action_id: str):
        self.edges.append({"src": a_id, "dst": action_id, "kind": "artifact->action"})

    def record(self, entry: Dict[str, Any]):
        self.audit.append(entry)

    def path_from_untrusted(self, a: Artifact) -> bool:
        """S1 as a graph query: does every evidence path of the artifact start in domain U?"""
        if not self.enabled:
            return False
        return bool(a.domains) and all(d == "U" for d in a.domains)


class EIEPDetector:
    """Decision rule (section 7.3): EIEP iff (S1 or S2) and S3 and S4. S5/S6 raise risk only."""

    @staticmethod
    def decide(sig: Signals, artifact: Artifact) -> str:
        if sig.eiep:
            return "block"
        if sig.s3_boundary_crossing and (sig.s5_deviation or sig.s6_generalization):
            return "allow_audit"
        if sig.s3_boundary_crossing:
            return "allow_audit"
        return "allow"
