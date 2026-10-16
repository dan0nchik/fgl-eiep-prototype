"""Component ②: append-only provenance journal protected by a hash chain."""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

from .types import EnvFingerprint, Observation


class ProvenanceJournal:
    def __init__(self):
        self.records: List[Observation] = []
        self._by_id: Dict[str, Observation] = {}

    def append(self, command: str, output: str, exit_code: int, env: EnvFingerprint, kind: str = "exec") -> Observation:
        prev = self.records[-1].hash if self.records else ""
        o = Observation(id=f"o{len(self.records)+1}-{uuid.uuid4().hex[:6]}", command=command, output=output,
                        exit_code=exit_code, env=env, domain=env.domain, ts=time.time(), kind=kind, prev_hash=prev)
        o.hash = o.compute_hash()
        self.records.append(o)
        self._by_id[o.id] = o
        return o

    def get(self, oid: str) -> Optional[Observation]:
        return self._by_id.get(oid)

    def verify_chain(self) -> bool:
        prev = ""
        for o in self.records:
            if o.prev_hash != prev or o.compute_hash() != o.hash:
                return False
            prev = o.hash
        return True

    def tagged_output(self, o: Observation) -> str:
        """What the agent sees: tool output carrying its domain label."""
        return f"[domain={o.domain} location={o.env.location} obs={o.id} exit={o.exit_code}]\n{o.output}"

    def session(self, since: int) -> List[Observation]:
        return self.records[since:]
