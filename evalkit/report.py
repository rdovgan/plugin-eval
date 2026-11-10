"""Markdown evidence card for comparing two versions. Called from compare.py --report."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict

from .compare import ITERATIONS, SEED
from .config import ROOT

REPORTS = ROOT / "reports"


def _money(v: Any) -> str:
    return f"${float(v):.2f}" if v is not None else "—"


def render(plugin: str, ref_a: str, ref_b: str, model: str, ma: Dict[str, Any], mb: Dict[str, Any],
           r: Dict[str, Any]) -> str:
    lo, hi = r["ci"]
    lines = [
        f"# {plugin}: {ref_b} vs {ref_a} · {model}",
        "",
        f"**Verdict: {r['verdict']}.** Mean score difference {r['mean_diff']:+.3f}, "
        f"95% interval [{lo:+.3f}, {hi:+.3f}] over {r['n']} cases.",
        "",
        "| | " + ref_a + " | " + ref_b + " |",
        "|---|---|---|",
        f"| Commit | `{ma['commit'][:10]}` | `{mb['commit'][:10]}` |",
        f"| Overall score | {ma.get('overall_score')} | {mb.get('overall_score')} |",
        f"| Cost | {_money(ma.get('cost_usd'))} | {_money(mb.get('cost_usd'))} |",
        f"| Time, s | {ma.get('duration_sec')} | {mb.get('duration_sec')} |",
        f"| Run date | {ma['created_at']} | {mb['created_at']} |",
        "",
        "## Cases",
        "",
        "| Case | " + ref_a + " | " + ref_b + " | Δ | Spread A / B | Errors |",
        "|---|---|---|---|---|---|",
    ]
    for row in sorted(r["rows"], key=lambda x: x["diff"]):
        mark = " (control)" if row["control"] else ""
        flag = " ⚠️" if row["diff"] < 0 else ""
        lines.append(f"| {row['case']}{mark} | {row['a']:.2f} | {row['b']:.2f} | {row['diff']:+.2f}{flag} | "
                     f"{row['stdev_a']:.2f} / {row['stdev_b']:.2f} | {row['errors']} |")
    if r["control_regressions"]:
        lines += ["", "**Regressed control cases:** " + ", ".join(r["control_regressions"])]
    if r["only_in_a"] or r["only_in_b"]:
        lines += ["", f"Cases only in {ref_a}: {', '.join(r['only_in_a']) or '—'}; "
                      f"only in {ref_b}: {', '.join(r['only_in_b']) or '—'}."]
    lines += [
        "",
        "## How it was obtained",
        "",
        f"- Case suite: `{mb['suite_hash']}`, attempts per case: {mb['runs']}"
        f"{', smoke' if mb.get('smoke') else ''}{', with the hidden set' if mb.get('hidden') else ''}",
        f"- MCP mocks: {', '.join(mb.get('mocked_servers') or []) or '—'}",
        f"- Model: `{mb['model']}`{' via ' + mb['base_url'] if mb.get('base_url') else ''}; "
        f"judge: `{mb['judge_model']}`",
        f"- Claude Code: {ma['claude_version']} / {mb['claude_version']}",
        f"- Interval: percentile bootstrap over cases, {ITERATIONS} iterations, seed {SEED}",
        f"- Raw results: `{Path(ma['_dir']).name}`, `{Path(mb['_dir']).name}` in results/",
        "",
        f"_Generated {dt.datetime.now().isoformat(timespec='minutes')}._",
    ]
    return "\n".join(lines) + "\n"


def write(plugin: str, ref_a: str, ref_b: str, model: str, ma, mb, result) -> Path:
    (REPORTS / plugin).mkdir(parents=True, exist_ok=True)
    safe = lambda s: s.replace("/", "_")
    path = REPORTS / plugin / f"{safe(ref_b)}-vs-{safe(ref_a)}__{model}{'__smoke' if mb.get('smoke') else ''}.md"
    path.write_text(render(plugin, ref_a, ref_b, model, ma, mb, result), encoding="utf-8")
    return path
