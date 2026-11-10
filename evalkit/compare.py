"""Paired comparison of two plugin versions on one model.

    python -m evalkit.compare --plugin java-developer --a v0.9.0 --b HEAD --model sonnet
    python -m evalkit.compare --plugin qa-docs --a v0.1.0 --b v0.2.0 --model sonnet --report

Verdict rule (from the requirements document):
  better        — the lower bound of the 95% interval is > 0 and no control case regressed
  worse         — the upper bound is < 0
  inconclusive  — everything else
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import aggregate, store

ITERATIONS = 5000
SEED = 1234          # fixed, so the same input gives the same interval
CONTROL_TAG = "control"


def bootstrap_ci(diffs: List[float], iterations: int = ITERATIONS, seed: int = SEED,
                 alpha: float = 0.05) -> Tuple[float, float]:
    """Percentile bootstrap of the mean difference: resampling cases with replacement."""
    if not diffs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choice(diffs) for _ in range(n)) / n for _ in range(iterations))
    lo = means[int((alpha / 2) * iterations)]
    hi = means[min(iterations - 1, int((1 - alpha / 2) * iterations))]
    return (lo, hi)


def verdict(ci: Tuple[float, float], control_regressions: List[str]) -> str:
    lo, hi = ci
    if lo > 0 and not control_regressions:
        return "better"
    if hi < 0:
        return "worse"
    return "inconclusive"


def compare(a: Dict[str, Any], b: Dict[str, Any], tags: Dict[str, List[str]]) -> Dict[str, Any]:
    """a, b — results of aggregate.case_scores; tags — {case: [tags]}."""
    common = sorted(set(a) & set(b))
    rows, diffs, control_regressions = [], [], []
    for name in common:
        sa, sb = a[name]["score"], b[name]["score"]
        if sa is None or sb is None:
            continue
        d = sb - sa
        diffs.append(d)
        is_control = CONTROL_TAG in tags.get(name, [])
        if is_control and d < 0:
            control_regressions.append(name)
        rows.append({"case": name, "a": sa, "b": sb, "diff": d, "control": is_control,
                     "stdev_a": a[name]["stdev"], "stdev_b": b[name]["stdev"],
                     "errors": a[name]["errors"] + b[name]["errors"]})
    ci = bootstrap_ci(diffs)
    mean = sum(diffs) / len(diffs) if diffs else 0.0
    return {
        "rows": rows, "mean_diff": mean, "ci": ci,
        "verdict": verdict(ci, control_regressions) if diffs else "inconclusive",
        "control_regressions": control_regressions,
        "only_in_a": sorted(set(a) - set(b)), "only_in_b": sorted(set(b) - set(a)),
        "n": len(diffs),
    }


def load_pair(plugin: str, ref_a: str, ref_b: str, model: str, smoke: bool, allow_cli_mismatch: bool):
    ma, mb = store.find_latest(plugin, ref_a, model, smoke), store.find_latest(plugin, ref_b, model, smoke)
    for ref, m in ((ref_a, ma), (ref_b, mb)):
        if not m:
            raise SystemExit(f"no completed run of {plugin} for {ref} × {model}"
                             f"{' (smoke)' if smoke else ''}. First run: python -m evalkit.run --plugins {plugin} --refs {ref} --models {model}")
    if ma["suite_hash"] != mb["suite_hash"]:
        raise SystemExit(f"different case suites: {ma['suite_hash']} vs {mb['suite_hash']}. "
                         f"Re-run the older version on the current cases.")
    if ma["claude_version"] != mb["claude_version"] and not allow_cli_mismatch:
        raise SystemExit(f"different Claude Code versions: {ma['claude_version']} vs {mb['claude_version']} "
                         f"(--allow-cli-mismatch if intentional)")
    return ma, mb


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plugin", required=True)
    p.add_argument("--a", required=True, help="baseline version (tag or commit)")
    p.add_argument("--b", required=True, help="new version")
    p.add_argument("--model", required=True)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--allow-cli-mismatch", action="store_true")
    p.add_argument("--report", action="store_true", help="write Markdown to reports/")
    args = p.parse_args(argv)

    ma, mb = load_pair(args.plugin, args.a, args.b, args.model, args.smoke, args.allow_cli_mismatch)
    sa = aggregate.case_scores(aggregate.load(Path(ma["_dir"]) / "aggregate.json"))
    sb = aggregate.case_scores(aggregate.load(Path(mb["_dir"]) / "aggregate.json"))
    tags = {c["name"]: c["tags"] for c in mb.get("cases", [])}
    result = compare(sa, sb, tags)

    lo, hi = result["ci"]
    print(f"{args.plugin}: {args.a} -> {args.b} on {args.model}: n={result['n']}  "
          f"Δ={result['mean_diff']:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]  =>  {result['verdict']}")
    print(f"cost: ${ma.get('cost_usd') or 0:.2f} -> ${mb.get('cost_usd') or 0:.2f}")
    if result["control_regressions"]:
        print("regressed control cases: " + ", ".join(result["control_regressions"]))

    path = None
    if args.report:
        from . import report
        path = report.write(args.plugin, args.a, args.b, args.model, ma, mb, result)
        print(f"report: {path}")
    from . import db
    db.try_record_comparison(args.plugin, args.model, args.a, args.b, ma, mb, result, path)
    from . import html_report
    html_report.main([])
    return {"better": 0, "inconclusive": 0, "worse": 1}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
