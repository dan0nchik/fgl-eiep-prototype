"""Offline replay of Hermes's built-in command detectors over every tool call in existing ASB trajectories.

No LLM calls. For each assistant tool call in gen_res.json, runs (via guards/hermes_guard.py, which imports
Hermes's own code) the individual detectors (hardline, sudo-stdin, DANGEROUS_PATTERNS + execution-flag findings,
tirith if installed) and Hermes's full headless gate check_all_command_guards (cron session, default config)
over the "<tool> <args-json>" rendering and every string argument value.

Usage: python hermes_offline_replay.py results/asb-gpt-4.1-mini-none/gen_res.json [--out results/x.json]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from guards.hermes_guard import TIRITH_AVAILABLE, builtin_gate, candidate_strings, detect


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gen")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    data = json.load(open(a.gen))
    n_calls = n_strings = 0
    flagged_calls, gate_blocks, cases_flagged, cases_gate = 0, 0, set(), set()
    kinds, descs, tools_flagged, examples = Counter(), Counter(), Counter(), []
    for ex in data:
        for m in ex.get("output", []):
            if m.get("role") != "assistant" or not m.get("tool_calls"):
                continue
            for tc in m["tool_calls"]:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                n_calls += 1
                n_strings += len(candidate_strings(name, args))
                f = detect(name, args)
                ok, msg = builtin_gate(name, args)
                if any(f.values()):
                    flagged_calls += 1
                    cases_flagged.add(ex["id"])
                    tools_flagged[name] += 1
                    for k, v in f.items():
                        if v:
                            kinds[k] += 1
                            for d in v:
                                descs[d] += 1
                    if len(examples) < 50:
                        examples.append({"id": ex["id"], "tool": name, "found": f, "gate_blocks": not ok,
                                         "args": json.dumps(args, ensure_ascii=False)[:300]})
                if not ok:
                    gate_blocks += 1
                    cases_gate.add(ex["id"])
    out = {
        "gen": a.gen, "n_cases": len(data), "n_tool_calls": n_calls, "n_strings_scanned": n_strings,
        "tirith_available": TIRITH_AVAILABLE,
        "flagged_tool_calls": flagged_calls,
        "flagged_tool_call_rate_pct": round(100.0 * flagged_calls / max(1, n_calls), 2),
        "cases_with_flagged_call": len(cases_flagged),
        "builtin_gate_blocks": gate_blocks, "cases_with_builtin_gate_block": len(cases_gate),
        "flag_kinds": dict(kinds), "flag_descriptions": dict(descs.most_common()),
        "flagged_tools": dict(tools_flagged.most_common()), "examples": examples,
    }
    outp = Path(a.out) if a.out else Path(a.gen).parent.parent / "hermes_offline_firerate.json"
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in out.items() if k != "examples"}, ensure_ascii=False, indent=2))
    print("saved", outp)


if __name__ == "__main__":
    main()
