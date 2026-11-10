"""Прогін кейсів проти версій плагінів та моделей.

    python -m evalkit.run --refs HEAD --models haiku --smoke                 # усі плагіни, smoke
    python -m evalkit.run --plugins java-developer --refs v0.10.0 HEAD --models sonnet
    python -m evalkit.run --plugins qa-docs --refs HEAD --models haiku --case 'qd-ask-*' --runs 1
    python -m evalkit.run --refs HEAD --models sonnet --hidden               # + прихований набір
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from . import aggregate, db, store, tracker
from .config import ROOT, Config, ModelProfile, PluginProfile, load

SUITES = ROOT / "suites"


def sh(*cmd: str, cwd: Path | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def cli_version() -> str:
    return sh("claude", "--version").split()[0]


def resolve_commit(repo: Path, ref: str) -> str:
    try:
        return sh("git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except subprocess.CalledProcessError:
        raise SystemExit(f"у {repo} немає тегу, гілки чи коміту '{ref}'")


def add_worktree(repo: Path, commit: str) -> Path:
    wt = Path(tempfile.mkdtemp(prefix=f"pe-{commit[:8]}-"))
    wt.rmdir()  # git worktree add хоче, щоб теки не було
    sh("git", "-C", str(repo), "worktree", "add", "--detach", str(wt), commit)
    return wt


def remove_worktree(repo: Path, wt: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
    shutil.rmtree(wt, ignore_errors=True)


def suite_dirs(plugin: str, hidden: bool) -> List[Path]:
    roots = [SUITES / plugin / "cases"] + ([SUITES / plugin / "hidden"] if hidden else [])
    return store.case_dirs(*roots)


def run_one(cfg: Config, plug: PluginProfile, plugin_dir: Path, profile: ModelProfile, runs: int,
            tags: List[str], case_glob: Optional[str], max_cost: float, out: Path, keep_temp: bool = False) -> int:
    cmd = ["claude", "plugin", "eval", str(plugin_dir),
           "--eval-dir", cfg.eval_dir_name,
           "--ablation", "none",
           "--runs", str(runs),
           "--model", profile.model,
           "--judge-model", cfg.judge_model,
           "--concurrency", str(cfg.concurrency),
           "--scaffold",                    # кейси самі будують робочий простір (tracker.scaffold_script)
           "--trust-plugin", "--no-publish",
           "--max-cost-usd", f"{max_cost:.2f}",
           "--json", str(out)]
    if case_glob:
        cmd += ["--case", case_glob]
    if keep_temp:
        cmd.append("--keep-temp")              # зберегти робочий простір і trace.jsonl кожного прогону
    if tags:
        cmd += ["--tag", *tags]
    if plug.allow_tools:
        cmd += ["--allow-tools", *plug.allow_tools]
    env = {**os.environ, **profile.env}
    print("  $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, env=env, timeout=cfg.timeout_sec).returncode


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plugins", nargs="+", help="імена з config.yaml (за замовчуванням усі)")
    p.add_argument("--refs", nargs="+", required=True, help="git-теги, гілки або коміти репозиторію плагіна")
    p.add_argument("--models", nargs="+", required=True, help="імена профілів з config.yaml")
    p.add_argument("--smoke", action="store_true", help="лише кейси з smoke-тегами, менше повторів")
    p.add_argument("--hidden", action="store_true", help="додати кейси з suites/<plugin>/hidden/")
    p.add_argument("--case", help="glob імені кейсу (для налагодження одного кейсу)")
    p.add_argument("--runs", type=int, help="перевизначити кількість повторів")
    p.add_argument("--force", action="store_true", help="ігнорувати кеш")
    p.add_argument("--keep-temp", action="store_true", help="зберегти робочі теки й трейси прогонів")
    args = p.parse_args(argv)

    cfg = load()
    plugins = [cfg.plugin(n) for n in (args.plugins or list(cfg.plugins))]
    profiles = [cfg.model(m) for m in args.models]   # падає одразу, якщо бракує змінних
    runs = args.runs or (cfg.smoke_runs if args.smoke else cfg.runs)
    tags = cfg.smoke_tags if args.smoke else []
    version = cli_version()
    spent_now = 0.0

    for plug in plugins:
        dirs = suite_dirs(plug.name, args.hidden)
        if not dirs:
            print(f"[{plug.name}] немає кейсів у suites/{plug.name}/cases", file=sys.stderr)
            continue
        # Хеш набору включає трекер: змінився тікет або синтетичний проєкт - кеш недійсний.
        suite = store.suite_hash([*dirs, tracker.TRACKER])
        print(f"[{plug.name}] кейсів: {len(dirs)}  suite={suite}  runs={runs}  claude={version}")

        for ref in args.refs:
            commit = resolve_commit(plug.repo, ref)
            pending = []
            for prof in profiles:
                key = store.cache_key(plugin=plug.name, commit=commit, model=prof.public_fingerprint(),
                                      suite=suite, runs=runs, tags=tags, case=args.case,
                                      judge=cfg.judge_model, claude=version)
                if not args.force and store.cached(key):
                    print(f"  [кеш] {ref} ({commit[:8]}) × {prof.name} -> results/{key}")
                else:
                    pending.append((prof, key))
            if not pending:
                continue

            wt = add_worktree(plug.repo, commit)
            try:
                plugin_dir = (wt / plug.subdir).resolve()
                if not (plugin_dir / ".claude-plugin" / "plugin.json").is_file():
                    print(f"  {ref}: у {plug.subdir} немає плагіна, пропускаю", file=sys.stderr)
                    continue
                mocked = tracker.build(plugin_dir, dirs, plugin_dir / cfg.eval_dir_name, cfg.maven_repo)
                for prof, key in pending:
                    remaining = min(cfg.budget_per_invocation - spent_now,
                                    cfg.budget_per_day - store.spent_today())
                    if remaining <= 0.01:
                        print(f"бюджет вичерпано (за запуск ${spent_now:.2f}, за день ${store.spent_today():.2f})",
                              file=sys.stderr)
                        return 2
                    print(f"  [прогін] {ref} ({commit[:8]}) × {prof.name}, моки: {', '.join(mocked) or '-'}, "
                          f"ліміт ${remaining:.2f}")
                    d = store.run_dir(key)
                    d.mkdir(parents=True, exist_ok=True)
                    out = d / "aggregate.json"
                    code = run_one(cfg, plug, plugin_dir, prof, runs, tags, args.case, remaining, out, args.keep_temp)
                    if not out.is_file():
                        print(f"    claude plugin eval завершився з кодом {code} без результату", file=sys.stderr)
                        continue
                    s = aggregate.summary(aggregate.load(out))
                    cost = float(s["cost_usd"] or 0)
                    spent_now += cost
                    store.log_cost(key, cost)
                    store.write_manifest(key, {
                        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
                        "plugin": plug.name, "ref": ref, "commit": commit,
                        "model_name": prof.name, **prof.public_fingerprint(),
                        "judge_model": cfg.judge_model, "mocked_servers": mocked,
                        "suite_hash": suite, "runs": runs, "smoke": args.smoke, "hidden": args.hidden,
                        "case_filter": args.case, "claude_version": version,
                        "cases": [store.case_meta(c) for c in dirs],
                        "exit_code": code, **s,
                    })
                    print(f"    score={s['overall_score']}  cost=${cost:.2f}  "
                          f"{'PARTIAL: ' + str(s['partial_reason']) if s['partial'] else 'ok'}")
                    db.try_record_run(key)
                    if s["partial"]:
                        if s.get("ungraded"):
                            print(f"    {s['ungraded']} запусків обірвались на помилці API без оцінювання "
                                  f"(найчастіше ліміт плану). Прогін не порахується в compare; зупиняюсь.",
                                  file=sys.stderr)
                        _refresh_html()
                        return 2
            finally:
                remove_worktree(plug.repo, wt)
    _refresh_html()
    return 0


def _refresh_html() -> None:
    from . import html_report
    try:
        html_report.main([])
    except Exception as e:  # noqa: BLE001 - звіт не повинен ламати прогін
        print(f"увага: HTML-звіт не оновлено ({e})", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
