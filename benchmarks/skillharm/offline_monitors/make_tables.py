"""Markdown tables from results/summary.json (score.py) for BASELINES_HERMES_NEMO.md."""
import json
import sys
from pathlib import Path

p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "results" / "summary.json"
S = json.loads(p.read_text())["monitors"]
ORDER = [m for m in ("hermes_builtin", "hermes_smart", "nemo_selfcheck", "fgl") if m in S]
NAMES = {"hermes_builtin": "Hermes builtin (headless gate)", "hermes_smart": "Hermes smart approval",
         "nemo_selfcheck": "NeMo self-check rails", "fgl": "FGL action monitor"}


def st(x):
    return f"{x['stopped']}/{x['of']} ({x['rate']}%)" if x["of"] else "n/a"


def wh(x):
    return f"{x['wh_asr']}%" if x.get("wh_asr") is not None else "n/a"


def fb(x):
    return f"{x['n']}/{x['of']} ({x['rate']}%)" if x["of"] else "n/a"


o0 = S[ORDER[0]]["overall"]
print(f"ASR(none) over attack trajectories with a deterministic outcome: {o0['n_success']}/{o0['n_asr_known']} "
      f"({o0['asr_none']}%).\n")
print("| monitor | stop: any block | stop: block at/before harm step | stop: block on an attack step | "
      "would-have-blocked ASR (any / by-harm / on-attack) | benign trajectories with any block | "
      "blocked non-attack steps | steps vetted / blocked |")
print("|---|---|---|---|---|---|---|---|")
for m in ORDER:
    o = S[m]["overall"]
    print(f"| {NAMES[m]} | {st(o['stop_any'])} | {st(o['stop_by_harm'])} | {st(o['stop_on_attack_step'])} | "
          f"{wh(o['stop_any'])} / {wh(o['stop_by_harm'])} / {wh(o['stop_on_attack_step'])} | "
          f"{fb(o['benign_false_block'])} | {fb(o['step_false_block_non_attack_steps'])} | "
          f"{o['steps_vetted']} / {o['steps_blocked']} |")
for dim, title in (("by_scenario", "scenario"), ("by_risk", "risk"), ("by_realization", "FPP realization")):
    print(f"\n**By {title}**: successful attacks stopped, 'on attack step' / 'any block'\n")
    keys = [k for k in S[ORDER[0]][dim] if k not in ("None", None)]
    print("| " + title + " | ASR(none) | " + " | ".join(NAMES[m] for m in ORDER) + " |")
    print("|---|---|" + "---|" * len(ORDER))
    for k in keys:
        b = S[ORDER[0]][dim][k]
        if not b["n_attack_traj"]:
            continue
        cells = []
        for m in ORDER:
            x = S[m][dim].get(k, {})
            cells.append(st(x["stop_on_attack_step"]) + " / any " + st(x["stop_any"]) if x else "-")
        print(f"| {k} | {b['n_success']}/{b['n_asr_known']} | " + " | ".join(cells) + " |")
