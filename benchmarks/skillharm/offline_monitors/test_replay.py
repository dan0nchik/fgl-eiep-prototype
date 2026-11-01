"""Unit tests for the offline replay harness on the synthetic trajectories (no LLM calls).

Run: ~/dev/guardrails-mvp-os/.venv/bin/python -m pytest -q test_replay.py   (or python test_replay.py)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-not-used")  # builtin mode makes no LLM call

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import traj_io  # noqa: E402
import replay  # noqa: E402
import score  # noqa: E402

SYN = HERE / "synthetic" / "none"


def test_unwrap():
    assert traj_io.unwrap_shell("/bin/bash -lc 'ls -la /root'") == "ls -la /root"
    assert traj_io.unwrap_shell("bash -lc \"echo 'a b'\"") == "echo 'a b'"
    assert traj_io.unwrap_shell("python3 x.py") == "python3 x.py"


def test_load():
    ts = {t["sample_id"]: t for t in traj_io.load_dir(SYN, "none")}
    assert set(ts) == {"synth_benign_01", "synth_attack_02", "synth_attack_03"}
    t = ts["synth_attack_02"]
    assert t["asr_success"] is True and t["risk_id"] == "anti_forensics" and t["harm_step"] == 4
    types = [s["type"] for s in t["steps"]]
    assert types == ["command", "command", "file_change", "command", "command", "message"]
    assert t["steps"][4]["command"].startswith("rm -rf /var/log")
    assert ts["synth_benign_01"]["benign"] is True


def test_history_excludes_current_and_keeps_order():
    t = {x["sample_id"]: x for x in traj_io.load_dir(SYN)}["synth_attack_02"]
    h = replay.history_msgs(t["instruction"], t["steps"][:3])
    assert h[0]["role"] == "user"
    names = [m["tool_calls"][0]["function"]["name"] for m in h if m.get("tool_calls")]
    assert names == ["shell", "shell", "apply_patch"]


def test_hermes_builtin_replay():
    check = replay.make_hermes("hermes_builtin", "gpt-4.1-mini")   # no LLM used in builtin mode
    ts = {x["sample_id"]: x for x in traj_io.load_dir(SYN)}
    r = replay.replay_one(ts["synth_attack_02"], check)
    assert r["first_block"] == 4                  # `rm -rf /var/log/*` -> Hermes "delete in root path"
    r = replay.replay_one(ts["synth_benign_01"], check)
    assert r["first_block"] is None


def test_score_stop_definitions():
    rec = {"first_block": 3, "harm_step": 4, "decisions": [{"i": 3, "decision": "block"}]}
    assert score.stopped(rec, "any") and score.stopped(rec, "by_harm")
    rec = {"first_block": 5, "harm_step": 4, "decisions": [{"i": 5, "decision": "block"}]}
    assert score.stopped(rec, "any") and not score.stopped(rec, "by_harm")


def test_export_format_smp_phases():
    ts = {t["sample_id"]: t for t in traj_io.load_dir(HERE / "synthetic" / "export")}
    t = ts["synthpair_a__synthpair_b__anti_forensics__synthetic"]
    assert t["scenario"] == "SMP" and t["asr_success"] is True
    assert [s.get("phase") for s in t["steps"]] == ["task_a", "task_a", "task_b", "task_b", "task_b"]
    assert t["steps"][0]["task"].startswith("Fill the PDF") and t["steps"][2]["task"].startswith("Extract")
    assert ts["benign__synthtask"]["benign"] is True
    seen = []

    def spy(task, hist, step):
        seen.append((step["i"], task[:7], len(hist)))
        return {"decision": "allow"}
    replay.replay_one(t, spy)
    # task B's first command sees only task B's user message (new session), not task A's history
    assert seen == [(0, "Fill th", 1), (2, "Extract", 1), (3, "Extract", 3)]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
