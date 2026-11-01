"""Print markdown tables from results/static_summary.json (for BASELINES_HERMES_NEMO.md)."""
import json
from pathlib import Path

S = json.loads((Path(__file__).parent / "results" / "static_summary.json").read_text())
H = S["hermes"]
NS, NF = S.get("nemo_selfcheck"), S.get("nemo_safety")


def f(n, d):
    return f"{n}/{d} ({100 * n / d:.1f}%)" if d else "n/a"


def row_keys():
    return list(H["by_risk_id"].keys())


print("| group | n | Hermes blocked (community) | Hermes blocked, attack-attributable | Hermes blocked on clean-passing skills | agent-created gate would refuse | NeMo self-check SKILL.md blocked | NeMo content-safety SKILL.md blocked | NeMo content-safety all text files blocked |")
print("|---|---|---|---|---|---|---|---|---|")


def line(label, h, ns, nf):
    n = h["n"]
    cols = [label, str(n), f(h["blocked"], n), f(h["attributable"], n),
            f(h["blocked_on_clean_allowed_skill"], h["n_on_clean_allowed_skill"]),
            f(h["agent_created_ask"], n),
            f(ns["blocked_skill_md"], ns["n"]) if ns else "pending",
            f(nf["blocked_skill_md"], nf["n"]) if nf else "pending",
            f(nf["blocked_all_text"], nf["n"]) if nf and "blocked_all_text" in nf else "n/a"]
    print("| " + " | ".join(cols) + " |")


line("**all poisoned (879)**", H["overall"], NS and NS["overall"], NF and NF["overall"])
for sc in ("FPP", "SMP"):
    line(f"**{sc}**", H["by_scenario"][sc], NS and NS["by_scenario"][sc], NF and NF["by_scenario"][sc])
for k in H["by_risk_id"]:
    line(k.replace("('", "").replace("')", "").replace("', '", " / "), H["by_risk_id"][k],
         NS and NS["by_risk_id"].get(k), NF and NF["by_risk_id"].get(k))
print()
print("| FPP realization / carrier | n | Hermes blocked | attack-attributable | NeMo self-check SKILL.md | NeMo safety SKILL.md | NeMo safety all text |")
print("|---|---|---|---|---|---|---|")
for dim in ("by_realization", "by_carrier"):
    for k, h in H[dim].items():
        if "SMP" in k:
            continue
        ns = NS and NS.get(dim, {}).get(k)
        nf = NF and NF.get(dim, {}).get(k)
        print(f"| {k.split(', ')[1].strip(chr(39) + ')')} | {h['n']} | {f(h['blocked'], h['n'])} | "
              f"{f(h['attributable'], h['n'])} | {f(ns['blocked_skill_md'], ns['n']) if ns else '-'} | "
              f"{f(nf['blocked_skill_md'], nf['n']) if nf else '-'} | "
              f"{f(nf['blocked_all_text'], nf['n']) if nf and 'blocked_all_text' in nf else '-'} |")
print()
c = H["clean"]
print("Clean originals:", json.dumps(c))
for nm, N in (("selfcheck", NS), ("safety", NF)):
    if N:
        print(nm, "clean", json.dumps(N["clean"]), "stats", json.dumps(N.get("stats")))
print("Hermes worst verdict per poisoned sample:", H["sample_worst_verdict"])
print("New high/critical patterns (poisoned vs clean):", H["new_high_critical_patterns_top"])
