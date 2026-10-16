"""Component ③: store of environment facts with scope, validity and evidence."""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

from .types import Fact


class FactStore:
    def __init__(self, ttl_s: Optional[float] = None):
        self.facts: List[Fact] = []
        self.ttl_s = ttl_s

    def add(self, text: str, scope_key: str, domain: str, observation_ids: List[str], status: str = "confirmed") -> Fact:
        f = Fact(id=f"f{len(self.facts)+1}-{uuid.uuid4().hex[:4]}", text=text, scope_key=scope_key, domain=domain,
                 observation_ids=list(observation_ids), status=status,
                 expires_at=(time.time() + self.ttl_s) if self.ttl_s else None)
        self.facts.append(f)
        return f

    def lookup(self, text: str, scope_key: str) -> Optional[Fact]:
        """A fact established in another scope is never transferred automatically (section 7.2, ③)."""
        for f in reversed(self.facts):
            if f.scope_key == scope_key and f.valid() and f.text.strip().lower() == text.strip().lower():
                return f
        return None

    def in_scope(self, scope_key: str) -> List[Fact]:
        return [f for f in self.facts if f.scope_key == scope_key and f.valid()]
