"""NVIDIA NeMo Guardrails (0.24.1) input rail as a skill-vetting analog on SkillHarm skills (poisoned vs clean).

NeMo has no skill-install hook. The closest analog is to treat the skill's text as an untrusted *user input* and
run the library's input rail over it: LLMRails.check([{"role":"user","content": chunk}], rail_types=[INPUT]).
We reuse benchmarks/agent_safetybench/guards/nemo_guard.py (real library, shipped prompts) for both variants:
  selfcheck : `self check input` with the library's example policy (verbatim examples/bots/abc/prompts.yml)
  safety    : `content safety check input $model=content_safety` (NemoGuard/Aegis 23-category prompt)
Guard model: gpt-4.1-mini. Fail-open on errors (counted).

Text: every text file of the skill directory, split per file into chunks of CHUNK chars (overlap OVERLAP).
A skill is "blocked" if ANY chunk is blocked. Two scopes are reported from the same calls:
  skill_md : only chunks of SKILL.md   (what the task statement asked for)
  all_text : chunks of all text files  (the payload may sit in a script / added doc)
Chunk verdicts are cached by sha256(variant|chunk) in results/nemo_chunk_cache_<variant>.json (hash + verdict
only, no text), so files shared by many samples are judged once.

Run with the NeMo venv:  ~/dev/venvs/nemo/bin/python nemo_static_scan.py --variant selfcheck
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "agent_safetybench"))
sys.path.insert(0, str(HERE.parents[1] / "tools"))
import os  # noqa: E402
import nemo_base_url_patch  # noqa: E402,F401  (routes NeMo to OPENAI_BASE_URL, e.g. the Codex shim)

import common as C  # noqa: E402
import smp_items  # noqa: E402

CHUNK, OVERLAP = 6000, 300


def chunks_of(text: str):
    if len(text) <= CHUNK:
        return [text]
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + CHUNK])
        if i + CHUNK >= len(text):
            break
        i += CHUNK - OVERLAP
    return out


def skill_chunks(skill_dir: Path):
    """[(relfile, chunk_hash, chunk_text)]"""
    out = []
    for f in C.text_files(skill_dir):
        t = C.read_text(f)
        if not t or not t.strip():
            continue
        rel = str(f.relative_to(skill_dir))
        for ch in chunks_of(t):
            out.append((rel, C.sha(ch, 24), ch))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="selfcheck", choices=["selfcheck", "safety"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default=os.environ.get("GUARD_MODEL", "gpt-4.1-mini"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--scope", default="all_text", choices=["all_text", "skill_md"],
                    help="which chunks to send (skill_md = cheaper, only SKILL.md)")
    a = ap.parse_args()

    from guards.nemo_guard import NemoGuard
    g = NemoGuard(a.variant, model=a.model)
    C.OUT_DIR.mkdir(exist_ok=True)
    cache_path = C.OUT_DIR / f"nemo_chunk_cache_{a.variant}.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    lock = threading.Lock()

    # enumerate units
    units = []   # (kind, record_base, skill_dir)
    clean_seen = set()
    for it in C.fpp_items():
        units.append(("poisoned", {k: it[k] for k in ("id", "uid", "scenario", "task_id", "risk_id", "realization",
                                                      "carrier_point_type", "skill", "target_rel", "added_rel")},
                      it["poisoned_dir"]))
        key = (it["task_id"], it["skill"])
        if key not in clean_seen and it["clean_dir"] is not None and it["clean_dir"].is_dir():
            clean_seen.add(key)
            units.append(("clean", {"task_id": it["task_id"], "skill": it["skill"], "scenario": "FPP"},
                          it["clean_dir"]))
    for it in smp_items.smp_items():
        for sk, d in it["stage1_dirs"].items():
            units.append(("poisoned", {"id": it["id"], "uid": it["uid"], "scenario": "SMP", "pair": it["pair"],
                                       "risk_id": it["risk_id"], "skill": sk, "stage": "stage1"}, d))
        for sk, d in it["clean_dirs"].items():
            key = ("SMP:" + it["pair"], sk)
            if key not in clean_seen:
                clean_seen.add(key)
                units.append(("clean", {"task_id": "SMP:" + it["pair"], "skill": sk, "scenario": "SMP"}, d))
    if a.limit:
        units = units[:a.limit]

    # unique chunks to judge
    unit_chunks = []
    todo = {}
    for kind, base, d in units:
        ch = skill_chunks(d)
        if a.scope == "skill_md":
            ch = [c for c in ch if c[0].lower() == "skill.md"]
        unit_chunks.append(ch)
        for rel, h, txt in ch:
            if h not in cache:
                todo[h] = txt
    print(f"{len(units)} units, {sum(len(c) for c in unit_chunks)} chunks, {len(todo)} uncached", flush=True)

    done = [0]

    def judge(item):
        h, txt = item
        try:
            r = g._run([{"role": "user", "content": txt}], "input")
            v = {"blocked": bool(r["blocked"]), "err": None}
        except Exception as e:  # fail-open, not cached
            v = {"blocked": False, "err": f"{type(e).__name__}"}
        with lock:
            if v["err"] is None:
                cache[h] = v["blocked"]
            done[0] += 1
            if done[0] % 50 == 0:
                print("judged", done[0], flush=True)
                cache_path.write_text(json.dumps(cache))
        return h, v

    errors = {}
    with ThreadPoolExecutor(a.workers) as ex:
        for h, v in ex.map(judge, list(todo.items())):
            if v["err"]:
                errors[h] = v["err"]
    cache_path.write_text(json.dumps(cache))

    res = {"variant": a.variant, "scope_sent": a.scope, "chunk_chars": CHUNK, "overlap": OVERLAP,
           "guard_model": a.model, "base_url": os.environ.get("OPENAI_BASE_URL", "api.openai.com"), "nemoguardrails": "0.24.1", "errors_fail_open": len(errors),
           "poisoned": [], "clean": [], "stats": g.stats()}
    for (kind, base, d), ch in zip(units, unit_chunks):
        rec = dict(base)
        blocked_files = sorted({rel for rel, h, _ in ch if cache.get(h)})
        rec["n_chunks"] = len(ch)
        rec["n_chunks_skill_md"] = sum(1 for rel, _, _ in ch if rel.lower() == "skill.md")
        rec["blocked_files"] = blocked_files
        rec["blocked_all_text"] = bool(blocked_files) if a.scope == "all_text" else None
        rec["blocked_skill_md"] = any(rel.lower() == "skill.md" and cache.get(h) for rel, h, _ in ch)
        rec["n_err_chunks"] = sum(1 for _, h, _ in ch if h not in cache)
        if rec["n_err_chunks"]:      # LLM failures are never counted as allow/block: unit is left undecided
            rec["blocked_all_text"] = None if not blocked_files else True
            if not rec["blocked_skill_md"] and any(rel.lower() == "skill.md" and h not in cache for rel, h, _ in ch):
                rec["blocked_skill_md"] = None
        res[kind].append(rec)
    out = C.OUT_DIR / f"nemo_static_scan_{a.variant}.json"
    out.write_text(json.dumps(res, indent=1))
    und = sum(1 for k in ("poisoned", "clean") for r in res[k] if r["n_err_chunks"])
    print("wrote", out, "chunk errors", len(errors), "units with undecided chunks", und,
          "-> re-run to fill" if und else "")


if __name__ == "__main__":
    main()
