"""Storage of runs in results/<key>/ and the spend ledger results/ledger.jsonl."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from .config import ROOT

RESULTS = ROOT / "results"
LEDGER = RESULTS / "ledger.jsonl"


# ---------- cases ----------

def case_dirs(*roots: Path) -> List[Path]:
    out = []
    for root in roots:
        if root.is_dir():
            out += sorted(p for p in root.iterdir() if p.is_dir() and
                          ((p / "prompt.md").is_file() or (p / "case.yaml").is_file()))
    return out


def suite_hash(dirs: Iterable[Path]) -> str:
    """Hash of the contents of all case files: one changed character gives a different hash and cache key."""
    h = hashlib.sha256()
    for d in sorted(dirs, key=lambda p: p.name):
        for f in sorted(p for p in d.rglob("*") if p.is_file()):
            h.update(f"{d.name}/{f.relative_to(d).as_posix()}\0".encode())
            h.update(f.read_bytes())
            h.update(b"\0")
    return h.hexdigest()[:16]


def read_frontmatter(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    return (yaml.safe_load(parts[1]) or {}) if len(parts) >= 3 else {}


def case_meta(d: Path) -> Dict[str, Any]:
    """Case name and tags. The `control` tag marks a control task."""
    meta: Dict[str, Any] = {}
    if (d / "case.yaml").is_file():
        meta.update(yaml.safe_load((d / "case.yaml").read_text(encoding="utf-8")) or {})
    if (d / "prompt.md").is_file():
        meta.update(read_frontmatter(d / "prompt.md"))
    return {"name": meta.get("name", d.name), "tags": list(meta.get("tags") or [])}


# ---------- cache key and runs ----------

def cache_key(**parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def run_dir(key: str) -> Path:
    return RESULTS / key


def cached(key: str) -> Optional[Dict[str, Any]]:
    """The cache hits only for a completed (not partial) run."""
    m = run_dir(key) / "manifest.json"
    if not m.is_file():
        return None
    manifest = json.loads(m.read_text(encoding="utf-8"))
    return None if manifest.get("partial") else manifest


def write_manifest(key: str, manifest: Dict[str, Any]) -> None:
    d = run_dir(key)
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def manifests() -> List[Dict[str, Any]]:
    out = []
    for m in sorted(RESULTS.glob("*/manifest.json")):
        data = json.loads(m.read_text(encoding="utf-8"))
        data["_dir"] = str(m.parent)
        out.append(data)
    return out


def find_latest(plugin: str, ref: str, model: str, smoke: bool) -> Optional[Dict[str, Any]]:
    """The latest completed full (no --case) run of the plugin for a tag/commit and model."""
    hits = [m for m in manifests()
            if not m.get("partial") and not m.get("case_filter") and m.get("plugin") == plugin
            and m.get("model_name") == model and bool(m.get("smoke")) == smoke
            and (m.get("ref") == ref or str(m.get("commit", "")).startswith(ref))]
    return max(hits, key=lambda m: m["created_at"]) if hits else None


# ---------- budget ----------

def log_cost(key: str, cost: float) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    entry = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
             "date": dt.date.today().isoformat(), "key": key, "cost_usd": cost}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def spent_today() -> float:
    if not LEDGER.is_file():
        return 0.0
    today = dt.date.today().isoformat()
    total = 0.0
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            if e.get("date") == today:
                total += float(e.get("cost_usd") or 0)
    return total
