"""Markdown-картка доказів для порівняння двох версій. Викликається з compare.py --report."""
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
        f"# {plugin}: {ref_b} проти {ref_a} · {model}",
        "",
        f"**Вердикт: {r['verdict']}.** Середня різниця балу {r['mean_diff']:+.3f}, "
        f"95% інтервал [{lo:+.3f}, {hi:+.3f}] на {r['n']} кейсах.",
        "",
        "| | " + ref_a + " | " + ref_b + " |",
        "|---|---|---|",
        f"| Коміт | `{ma['commit'][:10]}` | `{mb['commit'][:10]}` |",
        f"| Загальний бал | {ma.get('overall_score')} | {mb.get('overall_score')} |",
        f"| Вартість | {_money(ma.get('cost_usd'))} | {_money(mb.get('cost_usd'))} |",
        f"| Час, с | {ma.get('duration_sec')} | {mb.get('duration_sec')} |",
        f"| Дата прогону | {ma['created_at']} | {mb['created_at']} |",
        "",
        "## Кейси",
        "",
        "| Кейс | " + ref_a + " | " + ref_b + " | Δ | Розкид A / B | Помилки |",
        "|---|---|---|---|---|---|",
    ]
    for row in sorted(r["rows"], key=lambda x: x["diff"]):
        mark = " (контрольний)" if row["control"] else ""
        flag = " ⚠️" if row["diff"] < 0 else ""
        lines.append(f"| {row['case']}{mark} | {row['a']:.2f} | {row['b']:.2f} | {row['diff']:+.2f}{flag} | "
                     f"{row['stdev_a']:.2f} / {row['stdev_b']:.2f} | {row['errors']} |")
    if r["control_regressions"]:
        lines += ["", "**Погіршились контрольні кейси:** " + ", ".join(r["control_regressions"])]
    if r["only_in_a"] or r["only_in_b"]:
        lines += ["", f"Кейси лише в {ref_a}: {', '.join(r['only_in_a']) or '—'}; "
                      f"лише в {ref_b}: {', '.join(r['only_in_b']) or '—'}."]
    lines += [
        "",
        "## Як отримано",
        "",
        f"- Набір кейсів: `{mb['suite_hash']}`, повторів на кейс: {mb['runs']}"
        f"{', smoke' if mb.get('smoke') else ''}{', з прихованим набором' if mb.get('hidden') else ''}",
        f"- Моки MCP: {', '.join(mb.get('mocked_servers') or []) or '—'}",
        f"- Модель: `{mb['model']}`{' через ' + mb['base_url'] if mb.get('base_url') else ''}; "
        f"judge: `{mb['judge_model']}`",
        f"- Claude Code: {ma['claude_version']} / {mb['claude_version']}",
        f"- Інтервал: перцентильний бутстреп по кейсах, {ITERATIONS} ітерацій, seed {SEED}",
        f"- Сирі результати: `{Path(ma['_dir']).name}`, `{Path(mb['_dir']).name}` у results/",
        "",
        f"_Згенеровано {dt.datetime.now().isoformat(timespec='minutes')}._",
    ]
    return "\n".join(lines) + "\n"


def write(plugin: str, ref_a: str, ref_b: str, model: str, ma, mb, result) -> Path:
    (REPORTS / plugin).mkdir(parents=True, exist_ok=True)
    safe = lambda s: s.replace("/", "_")
    path = REPORTS / plugin / f"{safe(ref_b)}-vs-{safe(ref_a)}__{model}{'__smoke' if mb.get('smoke') else ''}.md"
    path.write_text(render(plugin, ref_a, ref_b, model, ma, mb, result), encoding="utf-8")
    return path
