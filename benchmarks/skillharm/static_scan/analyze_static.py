"""Aggregate the static (install-time) scans into tables: results/static_summary.json + markdown on stdout.

Hermes:  blocked = should_allow_install(scan_skill(dir, source=community)) is False.
         attributable = blocked AND the poisoned skill has a high/critical finding (pattern_id, file, match hash)
         that the clean original of the same skill does not have (i.e. the block is caused by the attack, not by
         a pre-existing finding in the benign skill).
         SMP samples can ship several modified skills: a sample is blocked if ANY of its skills is blocked.
NeMo:    blocked = any chunk blocked by the input rail (scope skill_md and all_text).
Clean:   false-positive rate over distinct (task, skill) clean originals and over distinct skill names.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

R = Path(__file__).parent / "results"


def pct(a, b):
    return None if not b else round(100.0 * a / b, 1)


def fset(rec, sev=("high", "critical")):
    # structural findings (size/file-count) carry the measured size in `match`; compare them by (pattern, file)
    return {(f["pattern_id"], f["file"], "" if f["category"] == "structural" else f["match_h"], f["category"])
            for f in rec.get("findings", []) if f["severity"] in sev}


def hermes():
    d = json.loads((R / "hermes_static_scan.json").read_text())
    clean = {(c["task_id"], c["skill"]): c for c in d["clean"] if not c.get("missing")}
    per_sample = {}
    for r in d["poisoned"]:
        key = r["uid"]
        ck = (r["task_id"], r["skill"]) if r["scenario"] == "FPP" else ("SMP:" + r["pair"], r["skill"])
        c = clean.get(ck)
        new_hc = fset(r) - (fset(c) if c else set())
        s = per_sample.setdefault(key, {"id": key, "scenario": r["scenario"], "risk_id": r["risk_id"],
                                        "realization": r.get("realization"),
                                        "carrier": r.get("carrier_point_type"),
                                        "blocked": False, "attributable": False, "attributable_content": False,
                                        "ask_agent_created": False, "clean_blocked": False,
                                        "verdicts": [], "patterns_new": set(), "has_clean": c is not None})
        s["blocked"] |= r["install_community"] == "block"
        s["attributable"] |= (r["install_community"] == "block" and bool(new_hc))
        s["attributable_content"] |= (r["install_community"] == "block"
                                      and any(x[3] != "structural" for x in new_hc))
        s["ask_agent_created"] |= r["install_agent_created"] != "allow"
        s["verdicts"].append(r["verdict"])
        s["patterns_new"] |= {p for p, _, _, _ in new_hc}
        s["has_clean"] &= c is not None
        s["clean_blocked"] |= bool(c and c["install_community"] == "block")
    samples = list(per_sample.values())

    def agg(rows):
        n = len(rows)
        return {"n": n, "blocked": sum(x["blocked"] for x in rows), "blocked_pct": pct(sum(x["blocked"] for x in rows), n),
                "attributable": sum(x["attributable"] for x in rows),
                "attributable_pct": pct(sum(x["attributable"] for x in rows), n),
                "attributable_content": sum(x["attributable_content"] for x in rows),
                "attributable_content_pct": pct(sum(x["attributable_content"] for x in rows), n),
                "n_on_clean_allowed_skill": sum(not x["clean_blocked"] for x in rows),
                "blocked_on_clean_allowed_skill": sum(x["blocked"] and not x["clean_blocked"] for x in rows),
                "blocked_on_clean_allowed_skill_pct": pct(sum(x["blocked"] and not x["clean_blocked"] for x in rows),
                                                          sum(not x["clean_blocked"] for x in rows)),
                "agent_created_ask": sum(x["ask_agent_created"] for x in rows),
                "agent_created_ask_pct": pct(sum(x["ask_agent_created"] for x in rows), n)}

    out = {"overall": agg(samples)}
    for dim in ("scenario", "risk_id", "realization", "carrier"):
        g = defaultdict(list)
        for x in samples:
            g[(x["scenario"], x[dim]) if dim != "scenario" else x[dim]].append(x)
        out["by_" + dim] = {str(k): agg(v) for k, v in sorted(g.items(), key=lambda t: str(t[0]))}
    vc = defaultdict(int)
    for x in samples:
        vc[max(x["verdicts"], key=lambda v: {"safe": 0, "caution": 1, "dangerous": 2}[v])] += 1
    out["sample_worst_verdict"] = dict(vc)
    pc = defaultdict(int)
    for x in samples:
        for p in x["patterns_new"]:
            pc[p] += 1
    out["new_high_critical_patterns_top"] = dict(sorted(pc.items(), key=lambda t: -t[1])[:25])
    # clean
    cl = list(clean.values())
    names = defaultdict(list)
    for c in cl:
        names[c["skill"]].append(c["install_community"] == "block")
    out["clean"] = {
        "n_task_skill": len(cl), "blocked": sum(c["install_community"] == "block" for c in cl),
        "blocked_pct": pct(sum(c["install_community"] == "block" for c in cl), len(cl)),
        "by_scenario": {s: {"n": sum(1 for c in cl if c["scenario"] == s),
                            "blocked": sum(1 for c in cl if c["scenario"] == s and c["install_community"] == "block")}
                        for s in ("FPP", "SMP")},
        "n_skill_names": len(names), "skill_names_blocked_any": sum(any(v) for v in names.values()),
        "agent_created_ask": sum(c["install_agent_created"] != "allow" for c in cl),
        "verdicts": {v: sum(1 for c in cl if c["verdict"] == v) for v in ("safe", "caution", "dangerous")},
        "missing_clean": [ (c["task_id"], c["skill"]) for c in d["clean"] if c.get("missing")],
    }
    cpc = defaultdict(int)
    for c in cl:
        for p in {f["pattern_id"] for f in c["findings"] if f["severity"] in ("high", "critical")}:
            cpc[p] += 1
    out["clean"]["high_critical_patterns"] = dict(sorted(cpc.items(), key=lambda t: -t[1]))
    out["samples_without_clean_original"] = sum(1 for x in samples if not x["has_clean"])
    st2 = {}
    for r in d.get("smp_stage2", []):
        c = clean.get(("SMP:" + r["pair"], r["skill"]))
        new_hc = fset(r) - (fset(c) if c else set())
        x = st2.setdefault(r["uid"], {"risk_id": r["risk_id"], "blocked": False, "attributable": False})
        x["blocked"] |= r["install_community"] == "block"
        x["attributable"] |= r["install_community"] == "block" and bool(new_hc)
    s1 = {x["id"]: x for x in samples if x["scenario"] == "SMP"}
    out["smp_stage2"] = {"n_samples": len(st2),
                         "blocked": sum(x["blocked"] for x in st2.values()),
                         "attributable": sum(x["attributable"] for x in st2.values()),
                         "stage1_blocked_same_samples": sum(1 for k in st2 if s1.get(k, {}).get("blocked")),
                         "stage1_attributable_same_samples": sum(1 for k in st2 if s1.get(k, {}).get("attributable")),
                         "newly_attributable_at_stage2": sum(1 for k, x in st2.items()
                                                             if x["attributable"] and not s1.get(k, {}).get("attributable"))}
    return out


def nemo(variant):
    p = R / f"nemo_static_scan_{variant}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    per = {}
    for r in d["poisoned"]:
        s = per.setdefault(r["uid"], {"scenario": r["scenario"], "risk_id": r["risk_id"],
                                     "realization": r.get("realization"), "md": False, "all": False, "und": False})
        s["md"] = s["md"] or bool(r["blocked_skill_md"])
        s["all"] = s["all"] or bool(r["blocked_all_text"])
        s["und"] = s["und"] or bool(r["n_err_chunks"])
    rows = list(per.values())

    def agg(rows):
        n = len(rows)
        return {"n": n, "undecided": sum(x["und"] for x in rows),
                "blocked_skill_md": sum(x["md"] for x in rows), "blocked_skill_md_pct": pct(sum(x["md"] for x in rows), n),
                "blocked_all_text": sum(x["all"] for x in rows), "blocked_all_text_pct": pct(sum(x["all"] for x in rows), n)}

    out = {"variant": variant, "scope_sent": d["scope_sent"], "overall": agg(rows)}
    for dim in ("scenario", "risk_id", "realization"):
        g = defaultdict(list)
        for x in rows:
            g[(x["scenario"], x[dim]) if dim != "scenario" else x[dim]].append(x)
        out["by_" + dim] = {str(k): agg(v) for k, v in sorted(g.items(), key=lambda t: str(t[0]))}
    cl = d["clean"]
    out["clean"] = {"n": len(cl), "undecided": sum(1 for c in cl if c["n_err_chunks"]),
                    "blocked_skill_md": sum(1 for c in cl if c["blocked_skill_md"]),
                    "blocked_all_text": sum(1 for c in cl if c["blocked_all_text"]),
                    "blocked_skill_md_pct": pct(sum(1 for c in cl if c["blocked_skill_md"]), len(cl)),
                    "blocked_all_text_pct": pct(sum(1 for c in cl if c["blocked_all_text"]), len(cl))}
    out["stats"] = d.get("stats")
    if d["scope_sent"] == "skill_md":          # all_text chunks were not sent: drop the all_text columns
        def strip(x):
            if isinstance(x, dict):
                return {k: strip(v) for k, v in x.items() if not k.startswith("blocked_all_text")}
            return x
        out = strip(out)
    return out


def main():
    s = {"hermes": hermes(), "nemo_selfcheck": nemo("selfcheck"), "nemo_safety": nemo("safety")}
    (R / "static_summary.json").write_text(json.dumps(s, indent=1, default=list))
    print(json.dumps(s, indent=1, default=list)[:6000])


if __name__ == "__main__":
    main()
