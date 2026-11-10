"""Читання aggregate-result.json від `claude plugin eval` (schemaVersion 1).

Звірено з реальним прогоном (Claude Code 2.1.322): costUsd, durationSeconds, claudeVersion, partial,
aggregates.overallScore, cases[].name, cases[].aggregates.score, cases[].arms.with[] з полями
score, error, turns, costUsd, graders[] (name, passed, scored, explanation), mocks, tracePath.
Запасні імена ключів лишені на випадок змін схеми.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional


def load(path: Path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("schemaVersion")
    if version not in (None, 1):
        print(f"увага: schemaVersion={version}, скрипт писали під 1")
    return data


def _case_name(case: Dict[str, Any]) -> str:
    for key in ("name", "caseName", "case", "id"):
        if isinstance(case.get(key), str):
            return case[key]
    raise KeyError(f"не знайшов імені кейсу серед ключів {sorted(case)}")


def _run_score(run: Dict[str, Any]) -> Optional[float]:
    for key in ("score", "runScore"):
        if isinstance(run.get(key), (int, float)):
            return float(run[key])
    return None


def ungraded(run: Dict[str, Any]) -> bool:
    """Запуск обірвався до оцінювання (ліміт плану, rate limit, помилка API): бал 0 нічого не означає."""
    return bool(run.get("error")) and not run.get("graders")


def ungraded_count(data: Dict[str, Any]) -> int:
    return sum(1 for c in data.get("cases") or [] for runs in (c.get("arms") or {}).values()
               for r in runs or [] if ungraded(r))


def case_scores(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """{ім'я кейсу: {score, runs: [бали прогонів], errors: n}} для with-arm."""
    out: Dict[str, Dict[str, Any]] = {}
    for case in data.get("cases") or []:
        name = _case_name(case)
        score = (case.get("aggregates") or {}).get("score")
        runs = (case.get("arms") or {}).get("with") or []
        run_scores: List[float] = [s for s in (_run_score(r) for r in runs) if s is not None]
        out[name] = {
            "score": float(score) if score is not None else None,
            "runs": run_scores,
            "stdev": statistics.pstdev(run_scores) if len(run_scores) > 1 else 0.0,
            "errors": sum(1 for r in runs if r.get("error")),
            "ungraded": sum(1 for r in runs if ungraded(r)),
        }
    return out


def summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """partial=True і для прогонів з неоціненими запусками: такий бал не порівнюють і не кешують."""
    bad = ungraded_count(data)
    partial = bool(data.get("partial")) or bad > 0
    reason = data.get("partialReason") or (f"ungraded:{bad}" if bad else None)
    return {
        "cost_usd": data.get("costUsd"),
        "duration_sec": data.get("durationSeconds"),
        "claude_version": data.get("claudeVersion"),
        "overall_score": (data.get("aggregates") or {}).get("overallScore"),
        "partial": partial,
        "partial_reason": reason,
        "ungraded": bad,
    }
