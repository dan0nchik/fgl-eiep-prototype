"""Shared helpers for the SkillHarm static (install-time) scans.

Data locations (outside the repo; nothing from them is copied into the repo):
  SKILLHARM_HF  : huggingface_hub snapshot of osunlp/SkillHarm (CC-BY-4.0)
  SKILLSBENCH   : clone of github.com/benchflow-ai/skillsbench (clean / original skills)

Results written by the scanners hold only ids, verdicts, pattern ids, severities, relative file names and
short content hashes -- never matched text or payloads.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Iterator, List, Optional

SKILLHARM_HF = Path(os.environ.get("SKILLHARM_HF", str(Path.home() / "dev/bench/skillharm_hf")))
SKILLSBENCH = Path(os.environ.get("SKILLSBENCH", str(Path.home() / "dev/bench/skillsbench")))
# skillsbench@4e9eb449 (parent of a8eefb4fdd, which renamed mario-coin-counting's skills after SkillHarm was built)
SKILLSBENCH_LEGACY = Path(os.environ.get("SKILLSBENCH_LEGACY", str(Path.home() / "dev/bench/skillsbench_legacy")))
OUT_DIR = Path(__file__).parent / "results"

TEXT_EXT = {".md", ".txt", ".py", ".sh", ".bash", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".cfg",
            ".ini", ".r", ".rb", ".pl", ".html", ".css", ".csv", ".xml", ".sql", ".ipynb", ".tex", ".rst",
            ".mjs", ".cjs", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".lua", ".ps1", ".bat",
            ".env", ".conf", ".j2", ".jinja", ".tpl", ""}


def sha(s: str | bytes, n: int = 12) -> str:
    if isinstance(s, str):
        s = s.encode("utf-8", "replace")
    return hashlib.sha256(s).hexdigest()[:n]


def manifest() -> Dict:
    return json.loads((SKILLHARM_HF / "MANIFEST.json").read_text())


def clean_task_dir(task_id: str, skill: Optional[str] = None) -> Optional[Path]:
    for base in (SKILLSBENCH, SKILLSBENCH_LEGACY):
        for sub in ("tasks", "tasks-extra"):
            p = base / sub / task_id
            if p.is_dir() and (skill is None or (p / "environment/skills" / skill).is_dir()):
                return p
    return None


def fpp_items() -> Iterator[Dict]:
    """Yield one dict per FPP attack sample with the poisoned skill dir and the matching clean skill dir."""
    for e in manifest()["fpp"]:
        sdir = SKILLHARM_HF / e["path"]
        meta = json.loads((sdir / "metadata.json").read_text())
        root = meta["owning_skill_root"]                 # e.g. environment/skills/mesh-analysis
        ctask = clean_task_dir(e["task_id"], Path(root).name)
        yield {
            "id": e["sample_id"], "uid": e["task_id"] + "/" + e["sample_id"], "scenario": "FPP", "task_id": e["task_id"], "risk_id": e["risk_id"],
            "realization": e["realization"], "design_agent_id": e["design_agent_id"],
            "carrier_point_type": meta.get("carrier_point_type"),
            "skill": Path(root).name, "skill_root": root,
            "target_rel": str(Path(meta["target_task_relative_path"]).relative_to(root)),
            "added_rel": [str(Path(a["task_relative_path"]).relative_to(root))
                          for a in meta.get("added_artifacts", [])
                          if a["task_relative_path"].startswith(root + "/")],
            "poisoned_dir": sdir / root,
            "clean_dir": (ctask / root) if ctask else None,
        }


def text_files(skill_dir: Path) -> List[Path]:
    out = []
    for f in sorted(skill_dir.rglob("*")):
        if f.is_file() and not f.is_symlink() and f.suffix.lower() in TEXT_EXT:
            out.append(f)
    return out


def read_text(f: Path) -> Optional[str]:
    try:
        b = f.read_bytes()
    except OSError:
        return None
    if b"\x00" in b[:4096]:
        return None
    return b.decode("utf-8", "replace")
