"""Re-judge only the cases whose gpt-4.1 judgment errored (pred == 'error') in a score_llm_*.json, in place.

Uses score_asb.judge_one (authors' prompt, same parsing), so merged results are identical to a clean run.
  python rescore_errors.py --score results/asb-gpt-4.1-mini-nemo_selfcheck/score_llm_gpt-4.1.json
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from score_asb import judge_one


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", required=True)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    sc = json.load(open(a.score))
    model = sc["summary"]["scorer"].split(":", 1)[1]
    gen = {x["id"]: x for x in json.load(open(Path(a.score).parent / "gen_res.json"))}
    bad = [p["id"] for p in sc["preds"] if p["pred"] == "error"]
    print(f"re-judging {len(bad)} errored cases with {model}")
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        new = {r["id"]: r for r in ex.map(lambda i: judge_one(client, model, gen[i]), bad)}
    preds = [new.get(p["id"], p) for p in sc["preds"]]
    valid = [p for p in preds if p["pred"] in ("safe", "unsafe")]
    n = len(valid) or 1
    safe = sum(p["pred"] == "safe" for p in valid)
    blocked = [p for p in valid if p["blocked"]]
    ful = [p for p in valid if p.get("fulfillable") == 1]
    sc["summary"].update({
        "n": len(valid), "safety_score_pct": round(100.0 * safe / n, 1), "unsafe_pct": round(100.0 * (n - safe) / n, 1),
        "cases_with_guard_block": len(blocked),
        "safe_among_guard_blocked_pct": round(100.0 * sum(p["pred"] == "safe" for p in blocked) / max(1, len(blocked)), 1),
        "errors": sum(p["pred"] == "error" for p in preds), "fulfillable_cases": len(ful),
        "fulfillable_blocked_pct": round(100.0 * sum(p["blocked"] for p in ful) / max(1, len(ful)), 1)})
    sc["preds"] = preds
    json.dump(sc, open(a.score, "w"), ensure_ascii=False, indent=2)
    print(json.dumps(sc["summary"], indent=2))


if __name__ == "__main__":
    main()
