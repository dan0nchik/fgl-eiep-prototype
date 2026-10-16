"""Section 7.5: the four interception points, mapped to Hermes and OpenClaw.

This prototype drives its own minimal agent (agent/loop.py). For a real platform the same four calls are
wired to the platform's hooks; the sensor stays on the harness side so the fingerprint never depends on
data returned by the container. Hermes v0.19 offers: tool-call wrappers (tools/*), `skill_manage`
create/edit/patch (tools/skill_manager_tool.py) and `write_approval.stage_write` as the staging queue;
there is no pre-write hook, so the gate runs as a post-write scan of ~/.hermes/skills unless patched in.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .layer import FGL
from .sensor import Target


class PlatformAdapter:
    """Glue between a host agent platform and FGL. Subclass and call these from the platform's hooks."""

    def __init__(self, fgl: FGL):
        self.fgl = fgl

    # 1. before a tool / shell call: return None to allow, or a message that replaces the tool result
    def pre_tool(self, target: Target, task: str, command: str, reasoning: str = "") -> Dict[str, Any]:
        d = self.fgl.before_tool(target, task, command, reasoning)
        return {"allow": d.action != "block", "decision": d.to_dict()}

    # 2. after a tool result: the output is journaled by the sensor and returned with its domain label
    def post_tool(self, target: Target, command: str) -> str:
        _, _, oid = self.fgl.run_tool(target, command)
        return self.fgl.after_tool(oid)

    # 3. on skill / memory write (Hermes: skill_manage create|edit|patch; OpenClaw: memory/skill store)
    def on_write(self, kind: str, name: str, procedure: str, evidence_ids: List[str]) -> Dict[str, Any]:
        a = self.fgl.on_artifact_write(kind, name, procedure, evidence_ids)
        return {"status": a.status, "stage_for_approval": a.status in ("quarantined", "rejected"), "record": a.render()}

    # 4. on retrieval into context (Hermes: skill_view / skills_list; OpenClaw: memory recall)
    def on_retrieve(self) -> List[str]:
        return [a.render() for a in self.fgl.on_retrieve()]
