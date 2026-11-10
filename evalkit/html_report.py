"""Interactive HTML report over all runs in results/ (one self-contained file, no CDN).

    python -m evalkit.html_report                    # -> reports/index.html
    python -m evalkit.html_report --out /tmp/r.html --open

What it contains: filters (plugin, model, run), tiles with the headline numbers, case scores with attempt
dots, cost and turns per case, a trend across runs, a comparison of two runs with a bootstrap interval,
and a table of cases with every grader's verdict in every attempt.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from . import aggregate, store
from .config import ROOT

REPORTS = ROOT / "reports"
SUITES = ROOT / "suites"


def _case_descriptions() -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for prompt in SUITES.glob("*/*/*/prompt.md"):
        front = store.read_frontmatter(prompt)
        body = prompt.read_text(encoding="utf-8").split("---", 2)[-1].strip()
        out[prompt.parent.name] = {"description": front.get("description", ""), "prompt": body}
    return out


def _attempt(no: int, r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "no": no, "score": r.get("score"), "passed": r.get("passed"), "error": r.get("error"),
        "ungraded": aggregate.ungraded(r), "turns": r.get("turns"), "cost": r.get("costUsd"),
        "judgeCost": r.get("judgeCostUsd"), "duration": r.get("durationSeconds"),
        "mockCalls": ((r.get("mocks") or {}).get("calls") or {}).get("total"),
        "graders": [{"name": g.get("name"), "passed": g.get("passed"), "scored": g.get("scored"),
                     "weight": g.get("weight"), "explanation": g.get("explanation")}
                    for g in r.get("graders") or []],
    }


def collect() -> Dict[str, Any]:
    desc = _case_descriptions()
    runs: List[Dict[str, Any]] = []
    for m in store.manifests():
        path = Path(m["_dir"]) / "aggregate.json"
        if not path.is_file():
            continue
        agg = aggregate.load(path)
        tags = {c["name"]: c.get("tags") or [] for c in m.get("cases") or []}
        types: Dict[str, str] = {}
        cases = []
        for c in agg.get("cases") or []:
            for g in c.get("graders") or []:
                types[g["name"]] = g.get("type")
            attempts = [_attempt(i, r) for i, r in enumerate((c.get("arms") or {}).get("with") or [], 1)]
            graded = [a["score"] for a in attempts if not a["ungraded"] and a["score"] is not None]
            t = tags.get(c["name"], [])
            cases.append({
                "name": c["name"], "tags": t, "control": "control" in t,
                "score": (c.get("aggregates") or {}).get("score"),
                "stdev": statistics.pstdev(graded) if len(graded) > 1 else 0.0,
                "description": desc.get(c["name"], {}).get("description", ""),
                "prompt": desc.get(c["name"], {}).get("prompt", ""),
                "maxTurns": c.get("maxTurns"),
                "graderTypes": {g["name"]: g.get("type") for g in c.get("graders") or []},
                "attempts": attempts,
            })
        a = agg.get("aggregates") or {}
        runs.append({
            "key": Path(m["_dir"]).name, "plugin": m.get("plugin"), "ref": m.get("ref"),
            "commit": m.get("commit", ""), "modelName": m.get("model_name"), "model": m.get("model"),
            "baseUrl": m.get("base_url") or "", "judge": m.get("judge_model"), "created": m.get("created_at"),
            "suite": m.get("suite_hash"), "claude": m.get("claude_version"), "runsPerCase": m.get("runs"),
            "smoke": bool(m.get("smoke")), "hidden": bool(m.get("hidden")), "caseFilter": m.get("case_filter"),
            "cost": agg.get("costUsd"), "duration": agg.get("durationSeconds"),
            "overall": a.get("overallScore"), "passRate": a.get("overallPassRate"),
            "casesTotal": a.get("casesTotal"), "casesPassed": a.get("casesPassed"),
            "partial": bool(m.get("partial")) or aggregate.ungraded_count(agg) > 0,
            "partialReason": m.get("partial_reason"), "ungraded": aggregate.ungraded_count(agg),
            "cases": cases,
        })
    runs.sort(key=lambda r: r["created"] or "")
    return {"generated": dt.datetime.now().isoformat(timespec="minutes"), "runs": runs}


def render(data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("/*__DATA__*/null", payload)


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=str(REPORTS / "index.html"))
    p.add_argument("--open", action="store_true", help="open in the browser")
    args = p.parse_args(argv)
    data = collect()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"report: {out}  (runs: {len(data['runs'])})")
    if args.open:
        subprocess.run(["open", str(out)], check=False)
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plugin eval results</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10); --wash: rgba(11,11,11,0.04);
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
  --pos: #2a78d6; --neg: #e34948; --mid: #f0efec;
  --good: #0ca30c; --good-text: #006300; --warning: #fab219; --critical: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --wash: rgba(255,255,255,0.05);
    --s1: #3987e5; --s2: #d95926; --s3: #199e70;
    --pos: #3987e5; --neg: #e66767; --mid: #383835; --good-text: #0ca30c;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --wash: rgba(255,255,255,0.05);
  --s1: #3987e5; --s2: #d95926; --s3: #199e70;
  --pos: #3987e5; --neg: #e66767; --mid: #383835; --good-text: #0ca30c;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1180px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 20px; margin: 0; }
h2 { font-size: 15px; margin: 0 0 4px; }
.sub { color: var(--ink-2); font-size: 13px; }
header { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.filters { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; margin-bottom: 16px; }
.filters label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--ink-2); }
select, button { font: inherit; color: var(--ink); background: var(--surface); border: 1px solid var(--border);
  border-radius: 6px; padding: 6px 8px; }
select { min-width: 160px; max-width: 100%; }
button { cursor: pointer; }
button:hover, select:hover { background: var(--wash); }
.check { flex-direction: row !important; align-items: center; gap: 6px !important; padding-bottom: 8px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 760px) { .grid2 { grid-template-columns: 1fr; } }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.tile .k { font-size: 12px; color: var(--ink-2); }
.tile .v { font-size: 26px; font-weight: 600; margin-top: 2px; }
.tile .n { font-size: 12px; color: var(--muted); }
.banner { border-radius: 10px; padding: 10px 14px; margin-bottom: 16px; border: 1px solid var(--critical);
  display: flex; gap: 10px; align-items: flex-start; }
.banner .icon { color: var(--critical); font-weight: 700; }
.chart { width: 100%; overflow: hidden; }
svg text { fill: var(--ink-2); font-size: 12px; }
svg .tick { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--ink-2); margin: 6px 0; }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
#tip { position: fixed; pointer-events: none; z-index: 10; background: var(--surface); color: var(--ink);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px; max-width: 360px;
  box-shadow: 0 4px 16px rgba(0,0,0,.12); display: none; }
#tip b { font-weight: 600; }
#tip .row { display: flex; justify-content: space-between; gap: 16px; }
#tip .row span:last-child { font-variant-numeric: tabular-nums; }
.empty { color: var(--muted); padding: 24px 0; text-align: center; }
.verdict { display: flex; gap: 16px; flex-wrap: wrap; align-items: baseline; margin: 6px 0 10px; }
.verdict .big { font-size: 18px; font-weight: 600; }
.status { display: inline-flex; align-items: center; gap: 4px; font-weight: 600; }
.ok { color: var(--good-text); } .bad { color: var(--critical); } .na { color: var(--muted); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { font-weight: 600; color: var(--ink-2); cursor: pointer; user-select: none; white-space: nowrap; }
th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr.case:hover { background: var(--wash); cursor: pointer; }
.tag { display: inline-block; font-size: 11px; color: var(--ink-2); border: 1px solid var(--border);
  border-radius: 999px; padding: 0 6px; margin: 2px 4px 0 0; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; margin: 4px 0 10px; }
.chip { border-radius: 999px; padding: 3px 10px; font-size: 12px; }
.chip[aria-pressed="true"] { background: var(--ink); color: var(--surface); border-color: var(--ink); }
.mini { display: inline-block; width: 64px; height: 6px; background: var(--grid); border-radius: 3px; vertical-align: middle; margin-right: 6px; }
.mini > i { display: block; height: 6px; background: var(--s1); border-radius: 3px; }
.dots { white-space: nowrap; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 3px; vertical-align: middle; }
.details td { background: var(--wash); }
.details .desc { color: var(--ink-2); margin-bottom: 8px; }
.details pre { white-space: pre-wrap; font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 8px; margin: 0 0 10px; }
.gtable td, .gtable th { padding: 4px 8px; font-size: 12px; cursor: default; }
.gtable .expl { color: var(--muted); font-size: 11px; }
.scroll { overflow-x: auto; }
.err { color: var(--critical); font-size: 12px; margin: 4px 0; }
.foot { color: var(--muted); font-size: 12px; margin-top: 24px; }
</style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Plugin eval: run results</h1>
      <div class="sub" id="gen"></div>
    </div>
    <button id="theme" type="button" title="Light / dark theme">Theme: auto</button>
  </header>

  <div class="filters">
    <label>Plugin <select id="f-plugin"></select></label>
    <label>Model <select id="f-model"></select></label>
    <label>Run <select id="f-run"></select></label>
    <label class="check"><input type="checkbox" id="f-debug"> debug runs (--case)</label>
  </div>

  <div id="banner"></div>
  <div class="tiles" id="tiles"></div>

  <section class="card">
    <h2>Case scores</h2>
    <div class="sub">The bar is the case's mean score (0-1), dots are individual attempts. An empty circle with a cross is an attempt that aborted before grading.</div>
    <div class="chart" id="c-cases"></div>
  </section>

  <div class="grid2">
    <section class="card"><h2>Cost per attempt, $</h2><div class="sub">CLI estimate at list prices, including the judge</div><div class="chart" id="c-cost"></div></section>
    <section class="card"><h2>Agent turns per attempt</h2><div class="sub">Mean over attempts; the tick is the max_turns limit</div><div class="chart" id="c-turns"></div></section>
  </div>

  <section class="card">
    <h2>Trend across runs</h2>
    <div class="sub">Overall score of the plugin's full runs (no --case, no invalid ones), one line per model</div>
    <div class="legend" id="l-trend"></div>
    <div class="chart" id="c-trend"></div>
  </section>

  <section class="card">
    <h2>Comparison of two runs</h2>
    <div class="filters" style="margin:8px 0">
      <label>Baseline run (A) <select id="f-base"></select></label>
      <div class="sub" style="padding-bottom:8px">B is the run selected at the top</div>
    </div>
    <div id="cmp-summary"></div>
    <div class="legend"><span><i class="sw" style="background:var(--pos)"></i>B better than A</span><span><i class="sw" style="background:var(--neg)"></i>B worse than A</span></div>
    <div class="chart" id="c-diff"></div>
  </section>

  <section class="card">
    <h2>Cases</h2>
    <div class="sub">Click a row for every grader's verdict in every attempt. Click a header to sort.</div>
    <div class="chips" id="chips"></div>
    <div class="scroll"><table id="t-cases"></table></div>
  </section>

  <div class="foot">Source: results/&lt;key&gt;/aggregate.json and manifest.json. The comparison interval is a percentile bootstrap over cases (5000 iterations, seed 1234); the official verdict comes from <code>python -m evalkit.compare</code>.</div>
</main>
<div id="tip" role="tooltip"></div>

<script id="data" type="application/json">/*__DATA__*/null</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toFixed(d);
const money = (v) => (v === null || v === undefined) ? "—" : "$" + Number(v).toFixed(v < 1 ? 3 : 2);
const mean = (a) => a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;
const short = (c) => (c || "").slice(0, 8);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const state = { plugin: null, model: null, run: null, base: null, debug: false, tag: null, sort: ["name", 1], open: new Set() };

/* ---------- tooltip ---------- */
const tip = $("tip");
function showTip(ev, rows, title) {
  tip.replaceChildren();
  if (title) { const b = document.createElement("b"); b.textContent = title; tip.append(b); }
  for (const [k, v] of rows) {
    const r = document.createElement("div"); r.className = "row";
    const a = document.createElement("span"); a.textContent = k;
    const b = document.createElement("span"); b.textContent = v;
    r.append(a, b); tip.append(r);
  }
  tip.style.display = "block"; moveTip(ev);
}
function moveTip(ev) {
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + w > innerWidth - 8) x = ev.clientX - w - pad;
  if (y + h > innerHeight - 8) y = ev.clientY - h - pad;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
const hideTip = () => { tip.style.display = "none"; };

/* ---------- svg helpers ---------- */
function svgEl(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.append(e);
  return e;
}
function text(parent, x, y, s, attrs = {}) { const t = svgEl("text", { x, y, ...attrs }, parent); t.textContent = s; return t; }
// Horizontal bar with a rounded data end (4px) and a square end on the baseline.
function hbar(parent, x0, x1, y, h, fill) {
  const w = Math.max(0, x1 - x0); if (w < 0.5) return null;
  const r = Math.min(4, w, h / 2);
  const d = `M${x0},${y} H${x0 + w - r} Q${x0 + w},${y} ${x0 + w},${y + r} V${y + h - r} Q${x0 + w},${y + h} ${x0 + w - r},${y + h} H${x0} Z`;
  return svgEl("path", { d, fill }, parent);
}
function hbarLeft(parent, x1, x0, y, h, fill) {   // bar growing left from x0
  const w = Math.max(0, x0 - x1); if (w < 0.5) return null;
  const r = Math.min(4, w, h / 2);
  const d = `M${x0},${y} H${x1 + r} Q${x1},${y} ${x1},${y + r} V${y + h - r} Q${x1},${y + h} ${x1 + r},${y + h} H${x0} Z`;
  return svgEl("path", { d, fill }, parent);
}
function newSvg(container, height) {
  container.replaceChildren();
  const w = Math.max(320, container.clientWidth);
  const svg = svgEl("svg", { width: w, height, viewBox: `0 0 ${w} ${height}`, role: "img" }, container);
  return [svg, w];
}
function hit(parent, x, y, w, h, onMove, onClick) {   // the hover area is larger than the mark itself
  const r = svgEl("rect", { x, y, width: w, height: h, fill: "transparent" }, parent);
  r.addEventListener("mousemove", onMove); r.addEventListener("mouseleave", hideTip);
  if (onClick) { r.style.cursor = "pointer"; r.addEventListener("click", onClick); }
  return r;
}

/* ---------- data selection ---------- */
const comparable = (r) => !r.caseFilter && !r.partial;
function runsFor(plugin, model) {
  return DATA.runs.filter((r) => r.plugin === plugin && r.modelName === model && (state.debug || !r.caseFilter));
}
function runLabel(r) {
  const flags = [r.smoke ? "smoke" : "", r.caseFilter ? "case: " + r.caseFilter : "", r.partial ? "INVALID" : ""].filter(Boolean);
  return `${(r.created || "").replace("T", " ").slice(0, 16)} · ${r.ref} (${short(r.commit)})${flags.length ? " · " + flags.join(", ") : ""}`;
}
function fillSelect(sel, items, value) {
  sel.replaceChildren();
  for (const [v, label] of items) { const o = document.createElement("option"); o.value = v; o.textContent = label; sel.append(o); }
  if (items.some(([v]) => v === value)) sel.value = value; else if (items.length) sel.value = items[items.length - 1][0];
  return sel.value || null;
}
function current() { return DATA.runs.find((r) => r.key === state.run) || null; }

function latest(runs) {   // latest full valid run, else latest full, else any
  const r = [...runs].reverse();
  return r.find(comparable) || r.find((x) => !x.caseFilter) || r[0] || null;
}
function syncFilters() {
  const plugins = [...new Set(DATA.runs.map((r) => r.plugin))].sort();
  if (!plugins.includes(state.plugin)) state.plugin = (latest(DATA.runs) || {}).plugin;
  state.plugin = fillSelect($("f-plugin"), plugins.map((p) => [p, p]), state.plugin);
  const ofPlugin = DATA.runs.filter((r) => r.plugin === state.plugin);
  const models = [...new Set(ofPlugin.map((r) => r.modelName))].sort();
  if (!models.includes(state.model)) state.model = (latest(ofPlugin) || {}).modelName;
  state.model = fillSelect($("f-model"), models.map((m) => [m, m]), state.model);
  // the plugin has only debug runs - show them instead of an empty page
  if (!state.debug && !runsFor(state.plugin, state.model).length && ofPlugin.length) { state.debug = true; $("f-debug").checked = true; }
  const runs = runsFor(state.plugin, state.model);
  // default: the latest full valid run
  const pref = state.run && runs.some((r) => r.key === state.run) ? state.run
    : ([...runs].reverse().find(comparable) || runs[runs.length - 1] || {}).key;
  state.run = fillSelect($("f-run"), runs.map((r) => [r.key, runLabel(r)]), pref);
  const bases = DATA.runs.filter((r) => r.plugin === state.plugin && r.modelName === state.model && r.key !== state.run && !r.caseFilter);
  const cur = current();
  const prev = [...bases].reverse().find((r) => comparable(r) && cur && r.created < cur.created);
  state.base = fillSelect($("f-base"), [["", "—"], ...bases.map((r) => [r.key, runLabel(r)])],
    bases.some((r) => r.key === state.base) ? state.base : (prev ? prev.key : ""));
}

/* ---------- banner & tiles ---------- */
function renderBanner(run) {
  const b = $("banner"); b.replaceChildren();
  if (!run || !run.partial) return;
  const total = run.cases.reduce((s, c) => s + c.attempts.length, 0);
  const box = document.createElement("div"); box.className = "banner";
  const icon = document.createElement("span"); icon.className = "icon"; icon.textContent = "⚠ Invalid run";
  const msg = document.createElement("div");
  const errs = [...new Set(run.cases.flatMap((c) => c.attempts.filter((a) => a.ungraded).map((a) => a.error)))];
  msg.textContent = run.ungraded
    ? `${run.ungraded} of ${total} attempts aborted before grading and got 0 automatically. The run score does not reflect plugin quality and is excluded from comparison. Reason: ${errs.slice(0, 2).join("; ")}`
    : `The run did not finish (${run.partialReason || "partial"}). It is excluded from comparison.`;
  box.append(icon, msg); b.append(box);
}
function tile(k, v, n, cls) {
  const t = document.createElement("div"); t.className = "tile";
  const a = document.createElement("div"); a.className = "k"; a.textContent = k;
  const b = document.createElement("div"); b.className = "v" + (cls ? " " + cls : ""); b.textContent = v;
  t.append(a, b);
  if (n) { const c = document.createElement("div"); c.className = "n"; c.textContent = n; t.append(c); }
  return t;
}
function renderTiles(run) {
  const t = $("tiles"); t.replaceChildren();
  if (!run) return;
  const att = run.cases.flatMap((c) => c.attempts);
  const passed = att.filter((a) => a.passed).length;
  t.append(
    tile("Overall score", fmt(run.overall), "mean over cases, 0-1"),
    tile("Cases passed", `${run.casesPassed ?? "—"} / ${run.casesTotal ?? "—"}`, "case score = 1.0"),
    tile("Attempts passed", `${passed} / ${att.length}`, `${run.runsPerCase} attempts per case`),
    tile("Cost", money(run.cost), "CLI estimate at list prices"),
    tile("Duration", run.duration ? `${Math.round(run.duration / 60)} min` : "—", `${run.claude} · ${run.model}`),
    tile("Ungraded attempts", `${run.ungraded}`, run.ungraded ? "✗ API error / limit" : "✓ all graded", run.ungraded ? "bad" : "ok"),
  );
}

/* ---------- charts ---------- */
const LABEL_W = 230;
function caseLabel(c) { return c.name + (c.control ? " · control" : ""); }
function caseRows(run) { return [...run.cases].sort((a, b) => a.name.localeCompare(b.name)); }

function renderCases(run) {
  const box = $("c-cases");
  if (!run) { box.replaceChildren(Object.assign(document.createElement("div"), { className: "empty", textContent: "No runs" })); return; }
  const rows = caseRows(run), rowH = 28, top = 8, bottom = 26;
  const [svg, W] = newSvg(box, top + rows.length * rowH + bottom);
  const x0 = Math.min(LABEL_W, W * 0.42), x1 = W - 56, sx = (v) => x0 + (x1 - x0) * v;
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    svgEl("line", { x1: sx(t), x2: sx(t), y1: top, y2: top + rows.length * rowH, stroke: css("--grid"), "stroke-width": 1 }, svg);
    text(svg, sx(t), top + rows.length * rowH + 16, t.toFixed(2), { class: "tick", "text-anchor": "middle" });
  }
  svgEl("line", { x1: x0, x2: x0, y1: top, y2: top + rows.length * rowH, stroke: css("--axis") }, svg);
  rows.forEach((c, i) => {
    const y = top + i * rowH, mid = y + rowH / 2;
    text(svg, x0 - 8, mid + 4, caseLabel(c), { "text-anchor": "end" });
    hbar(svg, x0, sx(c.score || 0), mid - 5, 10, css("--s1"));
    c.attempts.forEach((a) => {
      if (a.ungraded) {
        const g = svgEl("g", {}, svg), cx = sx(0) + 6 + (a.no - 1) * 3;
        svgEl("circle", { cx, cy: mid, r: 5, fill: css("--surface"), stroke: css("--critical"), "stroke-width": 1.5 }, g);
        text(g, cx, mid + 3.5, "×", { "text-anchor": "middle", style: `fill:${css("--critical")};font-size:10px` });
      } else {
        svgEl("circle", { cx: sx(a.score || 0), cy: mid, r: 4.5, fill: css("--ink"), stroke: css("--surface"), "stroke-width": 2 }, svg);
      }
    });
    const ok = c.score === 1;
    text(svg, x1 + 8, mid + 4, `${fmt(c.score)}${ok ? " ✓" : ""}`, { style: `fill:${ok ? css("--good-text") : css("--ink-2")};font-variant-numeric:tabular-nums` });
    hit(svg, 0, y, W, rowH, (ev) => showTip(ev, [
      ["Case score", fmt(c.score)],
      ["Attempts", c.attempts.map((a) => a.ungraded ? "×" : fmt(a.score)).join("  ")],
      ["Spread σ", fmt(c.stdev)],
      ["Turns (avg)", fmt(mean(c.attempts.filter((a) => a.turns != null).map((a) => a.turns)), 1)],
      ["Cost per attempt", money(mean(c.attempts.filter((a) => a.cost != null).map((a) => a.cost + (a.judgeCost || 0))))],
      ["Failed", [...new Set(c.attempts.flatMap((a) => a.graders.filter((g) => g.scored !== false && !g.passed).map((g) => g.name)))].join(", ") || "—"],
    ], c.name), () => toggleCase(c.name, true));
  });
}

function renderMetric(boxId, run, valueOf, fmtv, limitOf) {
  const box = $(boxId);
  if (!run) { box.replaceChildren(); return; }
  const rows = caseRows(run).map((c) => ({ c, v: mean(c.attempts.filter((a) => !a.ungraded).map(valueOf).filter((x) => x != null)) }));
  const max = Math.max(1e-9, ...rows.map((r) => r.v || 0), ...rows.map((r) => (limitOf && limitOf(r.c)) || 0));
  const rowH = 22, top = 6, bottom = 24;
  const [svg, W] = newSvg(box, top + rows.length * rowH + bottom);
  const x0 = Math.min(LABEL_W - 40, W * 0.45), x1 = W - 64, sx = (v) => x0 + (x1 - x0) * (v / max);
  for (const t of [0, 0.5, 1]) {
    svgEl("line", { x1: sx(max * t), x2: sx(max * t), y1: top, y2: top + rows.length * rowH, stroke: css("--grid") }, svg);
    text(svg, sx(max * t), top + rows.length * rowH + 16, fmtv(max * t), { class: "tick", "text-anchor": "middle" });
  }
  rows.forEach(({ c, v }, i) => {
    const y = top + i * rowH, mid = y + rowH / 2;
    text(svg, x0 - 8, mid + 4, c.name, { "text-anchor": "end" });
    if (v != null) hbar(svg, x0, sx(v), mid - 4, 8, css("--s1"));
    const lim = limitOf && limitOf(c);
    if (lim) svgEl("line", { x1: sx(lim), x2: sx(lim), y1: mid - 7, y2: mid + 7, stroke: css("--ink-2"), "stroke-width": 2 }, svg);
    text(svg, x1 + 14, mid + 4, v == null ? "—" : fmtv(v), { style: "font-variant-numeric:tabular-nums" });
    hit(svg, 0, y, W, rowH, (ev) => showTip(ev, [["Mean", v == null ? "—" : fmtv(v)], ...(lim ? [["max_turns", String(lim)]] : [])], c.name));
  });
}

function renderTrend() {
  const box = $("c-trend"), legend = $("l-trend");
  legend.replaceChildren();
  const runs = DATA.runs.filter((r) => r.plugin === state.plugin && comparable(r));
  const models = [...new Set(runs.map((r) => r.modelName))].sort().slice(0, 3);   // ≤3 series: the validated part of the palette
  if (runs.length < 2) {
    box.replaceChildren(Object.assign(document.createElement("div"), { className: "empty",
      textContent: runs.length ? "Only one full valid run so far - the trend appears after the second." : "No full valid runs for this plugin." }));
    return;
  }
  const colors = ["--s1", "--s2", "--s3"].map(css);
  models.forEach((m, i) => { const s = document.createElement("span"); s.innerHTML = `<i class="sw" style="background:${colors[i]}"></i>`; s.append(m); legend.append(s); });
  const H = 240, top = 12, bottom = 40, left = 44;
  const [svg, W] = newSvg(box, H);
  const right = W - 90, n = runs.length;
  const sx = (i) => left + (n === 1 ? 0 : (right - left) * i / (n - 1)), sy = (v) => top + (H - top - bottom) * (1 - v);
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    svgEl("line", { x1: left, x2: right, y1: sy(t), y2: sy(t), stroke: css("--grid") }, svg);
    text(svg, left - 8, sy(t) + 4, t.toFixed(2), { class: "tick", "text-anchor": "end" });
  }
  runs.forEach((r, i) => text(svg, sx(i), H - bottom + 18, short(r.commit), { class: "tick", "text-anchor": "middle" }));
  models.forEach((m, mi) => {
    const pts = runs.map((r, i) => [i, r]).filter(([, r]) => r.modelName === m);
    if (!pts.length) return;
    svgEl("path", { d: pts.map(([i, r], k) => `${k ? "L" : "M"}${sx(i)},${sy(r.overall || 0)}`).join(" "),
      fill: "none", stroke: colors[mi], "stroke-width": 2, "stroke-linejoin": "round" }, svg);
    for (const [i, r] of pts) svgEl("circle", { cx: sx(i), cy: sy(r.overall || 0), r: 4, fill: colors[mi], stroke: css("--surface"), "stroke-width": 2 }, svg);
    const [li, lr] = pts[pts.length - 1];
    text(svg, sx(li) + 8, sy(lr.overall || 0) + 4, `${m} ${fmt(lr.overall)}`, { style: `fill:${css("--ink-2")}` });
  });
  const cross = svgEl("line", { y1: top, y2: H - bottom, stroke: css("--axis"), "stroke-width": 1, visibility: "hidden" }, svg);
  hit(svg, left, top, right - left, H - top - bottom, (ev) => {
    const rect = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round((ev.clientX - rect.left - left) / ((right - left) / Math.max(1, n - 1)))));
    cross.setAttribute("x1", sx(i)); cross.setAttribute("x2", sx(i)); cross.setAttribute("visibility", "visible");
    const r = runs[i];
    showTip(ev, [["Model", r.modelName], ["Score", fmt(r.overall)], ["Cases passed", `${r.casesPassed}/${r.casesTotal}`], ["Cost", money(r.cost)], ["Suite", r.suite]], `${r.ref} (${short(r.commit)}) · ${(r.created || "").slice(0, 10)}`);
  }).addEventListener("mouseleave", () => cross.setAttribute("visibility", "hidden"));
}

/* ---------- comparison ---------- */
function mulberry32(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function bootstrap(diffs, iters = 5000) {
  const rnd = mulberry32(1234), n = diffs.length, means = new Float64Array(iters);
  for (let k = 0; k < iters; k++) { let s = 0; for (let j = 0; j < n; j++) s += diffs[Math.floor(rnd() * n)]; means[k] = s / n; }
  means.sort();
  return [means[Math.floor(0.025 * iters)], means[Math.min(iters - 1, Math.floor(0.975 * iters))]];
}
function renderCompare(run) {
  const box = $("c-diff"), sum = $("cmp-summary");
  box.replaceChildren(); sum.replaceChildren();
  const base = DATA.runs.find((r) => r.key === state.base);
  const say = (s) => sum.append(Object.assign(document.createElement("div"), { className: "empty", textContent: s }));
  if (!run || !base) return say("Select a baseline run A of the same plugin and model.");
  const notes = [];
  if (run.partial || base.partial) notes.push("one of the runs is invalid (ungraded attempts) - the result is indicative only");
  if (run.suite !== base.suite) notes.push(`different case suites (${base.suite} vs ${run.suite})`);
  if (run.claude !== base.claude) notes.push(`different Claude Code versions (${base.claude} vs ${run.claude})`);
  const A = Object.fromEntries(base.cases.map((c) => [c.name, c])), B = Object.fromEntries(run.cases.map((c) => [c.name, c]));
  const rows = Object.keys(B).filter((k) => A[k] && A[k].score != null && B[k].score != null).sort()
    .map((k) => ({ name: k, a: A[k].score, b: B[k].score, d: B[k].score - A[k].score, control: B[k].control }));
  if (!rows.length) return say("No cases in common.");
  const diffs = rows.map((r) => r.d), [lo, hi] = bootstrap(diffs), m = mean(diffs);
  const ctrl = rows.filter((r) => r.control && r.d < 0).map((r) => r.name);
  const verdict = lo > 0 && !ctrl.length ? ["better", "ok", "▲"] : hi < 0 ? ["worse", "bad", "▼"] : ["inconclusive", "na", "●"];
  const v = document.createElement("div"); v.className = "verdict";
  v.innerHTML = `<span class="big status ${verdict[1]}"></span><span></span><span class="sub"></span>`;
  v.children[0].textContent = `${verdict[2]} ${verdict[0]}`;
  v.children[1].textContent = `Δ ${m >= 0 ? "+" : ""}${fmt(m, 3)} · 95% CI [${fmt(lo, 3)}, ${fmt(hi, 3)}] · n=${rows.length}`;
  v.children[2].textContent = `cost ${money(base.cost)} → ${money(run.cost)}${ctrl.length ? " · regressed control cases: " + ctrl.join(", ") : ""}`;
  sum.append(v);
  for (const nte of notes) sum.append(Object.assign(document.createElement("div"), { className: "err", textContent: "⚠ " + nte }));
  const rowH = 24, top = 6, bottom = 24;
  const [svg, W] = newSvg(box, top + rows.length * rowH + bottom);
  const x0 = Math.min(LABEL_W, W * 0.42), x1 = W - 56, zero = (x0 + x1) / 2, sx = (v) => zero + (x1 - x0) / 2 * v;
  for (const t of [-1, -0.5, 0, 0.5, 1]) {
    svgEl("line", { x1: sx(t), x2: sx(t), y1: top, y2: top + rows.length * rowH, stroke: t === 0 ? css("--axis") : css("--grid") }, svg);
    text(svg, sx(t), top + rows.length * rowH + 16, (t > 0 ? "+" : "") + t.toFixed(1), { class: "tick", "text-anchor": "middle" });
  }
  rows.forEach((r, i) => {
    const y = top + i * rowH, mid = y + rowH / 2;
    text(svg, x0 - 8, mid + 4, r.name + (r.control ? " · control" : ""), { "text-anchor": "end" });
    if (r.d > 0) hbar(svg, zero, sx(r.d), mid - 5, 10, css("--pos"));
    else if (r.d < 0) hbarLeft(svg, sx(r.d), zero, mid - 5, 10, css("--neg"));
    else svgEl("circle", { cx: zero, cy: mid, r: 3, fill: css("--muted") }, svg);
    text(svg, x1 + 8, mid + 4, (r.d > 0 ? "+" : "") + fmt(r.d), { style: "font-variant-numeric:tabular-nums" });
    hit(svg, 0, y, W, rowH, (ev) => showTip(ev, [["A", fmt(r.a)], ["B", fmt(r.b)], ["Δ", (r.d > 0 ? "+" : "") + fmt(r.d)]], r.name));
  });
}

/* ---------- table ---------- */
const COLS = [
  ["name", "Case", false], ["score", "Score", true], ["attempts", "Attempts", false], ["stdev", "σ", true],
  ["turns", "Turns", true], ["cost", "$ / attempt", true], ["duration", "s / attempt", true], ["ungraded", "Ungraded", true],
];
function caseMetrics(c) {
  const ok = c.attempts.filter((a) => !a.ungraded);
  return { name: c.name, score: c.score ?? -1, stdev: c.stdev, ungraded: c.attempts.length - ok.length,
    turns: mean(ok.map((a) => a.turns).filter((x) => x != null)), cost: mean(ok.map((a) => (a.cost || 0) + (a.judgeCost || 0))),
    duration: mean(ok.map((a) => a.duration).filter((x) => x != null)) };
}
function toggleCase(name, scroll) {
  if (state.open.has(name) && !scroll) state.open.delete(name); else state.open.add(name);
  renderTable(current());
  if (scroll) { const row = document.querySelector(`tr[data-case="${CSS.escape(name)}"]`); if (row) row.scrollIntoView({ behavior: "smooth", block: "center" }); }
}
function dotFor(a) {
  const d = document.createElement("span"); d.className = "dot";
  if (a.ungraded) { d.style.border = `1.5px solid ${css("--critical")}`; d.title = `attempt ${a.no}: not graded (${a.error})`; }
  else if (a.passed) { d.style.background = css("--good"); d.title = `attempt ${a.no}: passed (${fmt(a.score)})`; }
  else { d.style.background = css("--critical"); d.title = `attempt ${a.no}: ${fmt(a.score)}`; }
  return d;
}
function renderChips(run) {
  const box = $("chips"); box.replaceChildren();
  if (!run) return;
  const tags = [...new Set(run.cases.flatMap((c) => c.tags))].sort();
  for (const t of [null, ...tags]) {
    const b = document.createElement("button"); b.type = "button"; b.className = "chip";
    b.textContent = t === null ? "all" : t; b.setAttribute("aria-pressed", String(state.tag === t));
    b.addEventListener("click", () => { state.tag = t; renderChips(run); renderTable(run); });
    box.append(b);
  }
}
function renderTable(run) {
  const t = $("t-cases"); t.replaceChildren();
  if (!run) return;
  const thead = t.createTHead(), hr = thead.insertRow();
  for (const [key, label, num] of COLS) {
    const th = document.createElement("th"); th.textContent = label + (state.sort[0] === key ? (state.sort[1] > 0 ? " ▲" : " ▼") : "");
    if (num) th.className = "num";
    th.addEventListener("click", () => { state.sort = [key, state.sort[0] === key ? -state.sort[1] : 1]; renderTable(run); });
    hr.append(th);
  }
  const [sk, sd] = state.sort;
  const cases = run.cases.filter((c) => !state.tag || c.tags.includes(state.tag))
    .map((c) => [c, caseMetrics(c)])
    .sort(([, a], [, b]) => sk === "name" || sk === "attempts" ? sd * a.name.localeCompare(b.name) : sd * ((a[sk] ?? -1) - (b[sk] ?? -1)));
  const tb = t.createTBody();
  for (const [c, m] of cases) {
    const tr = tb.insertRow(); tr.className = "case"; tr.dataset.case = c.name;
    tr.addEventListener("click", () => toggleCase(c.name, false));
    const name = tr.insertCell();
    const strong = document.createElement("div"); strong.textContent = (state.open.has(c.name) ? "▾ " : "▸ ") + caseLabel(c); name.append(strong);
    for (const tag of c.tags) name.append(Object.assign(document.createElement("span"), { className: "tag", textContent: tag }));
    const sc = tr.insertCell(); sc.className = "num";
    const mini = document.createElement("span"); mini.className = "mini";
    mini.append(Object.assign(document.createElement("i"), { style: `width:${Math.round((c.score || 0) * 100)}%` }));
    sc.append(mini, document.createTextNode(fmt(c.score) + (c.score === 1 ? " ✓" : "")));
    const dots = tr.insertCell(); dots.className = "dots"; c.attempts.forEach((a) => dots.append(dotFor(a)));
    for (const [v, d] of [[m.stdev, 2], [m.turns, 1], [m.cost, 3], [m.duration, 0], [m.ungraded, 0]]) {
      const td = tr.insertCell(); td.className = "num"; td.textContent = fmt(v, d);
      if (d === 0 && v === m.ungraded && v > 0) td.classList.add("bad");
    }
    if (state.open.has(c.name)) renderDetails(tb, c);
  }
}
function renderDetails(tb, c) {
  const tr = tb.insertRow(); tr.className = "details";
  const td = tr.insertCell(); td.colSpan = COLS.length;
  td.append(Object.assign(document.createElement("div"), { className: "desc", textContent: c.description }));
  td.append(Object.assign(document.createElement("pre"), { textContent: c.prompt }));
  for (const a of c.attempts.filter((x) => x.error))
    td.append(Object.assign(document.createElement("div"), { className: "err", textContent: `✗ attempt ${a.no}: ${a.error}${a.ungraded ? " (not graded)" : ""}` }));
  const names = [...new Set(c.attempts.flatMap((a) => a.graders.map((g) => g.name)))].sort();
  if (!names.length) return;
  const wrap = document.createElement("div"); wrap.className = "scroll";
  const g = document.createElement("table"); g.className = "gtable";
  const h = g.createTHead().insertRow();
  for (const s of ["Grader", "Type", "Weight", ...c.attempts.map((a) => `Attempt ${a.no}`)]) h.append(Object.assign(document.createElement("th"), { textContent: s }));
  const body = g.createTBody();
  for (const n of names) {
    const r = body.insertRow();
    r.insertCell().textContent = n;
    r.insertCell().textContent = c.graderTypes[n] || "";
    const anyG = c.attempts.flatMap((a) => a.graders).find((x) => x.name === n);
    r.insertCell().textContent = anyG ? String(anyG.weight ?? "") : "";
    for (const a of c.attempts) {
      const cell = r.insertCell(), gr = a.graders.find((x) => x.name === n);
      const st = document.createElement("div");
      if (!gr) { st.className = "status na"; st.textContent = a.ungraded ? "not graded" : "—"; }
      else if (gr.scored === false) { st.className = "status na"; st.textContent = (gr.passed ? "✓" : "✗") + " indicator"; }
      else { st.className = "status " + (gr.passed ? "ok" : "bad"); st.textContent = gr.passed ? "✓ yes" : "✗ no"; }
      cell.append(st);
      if (gr && gr.explanation) cell.append(Object.assign(document.createElement("div"), { className: "expl", textContent: gr.explanation.length > 160 ? gr.explanation.slice(0, 160) + "…" : gr.explanation, title: gr.explanation }));
    }
  }
  wrap.append(g); td.append(wrap);
}

/* ---------- wiring ---------- */
function renderAll() {
  syncFilters();
  const run = current();
  $("gen").textContent = `Generated ${DATA.generated.replace("T", " ")} · runs in results/: ${DATA.runs.length}`;
  renderBanner(run); renderTiles(run); renderCases(run);
  renderMetric("c-cost", run, (a) => a.cost == null ? null : a.cost + (a.judgeCost || 0), (v) => "$" + v.toFixed(v < 0.1 ? 3 : 2));
  renderMetric("c-turns", run, (a) => a.turns, (v) => v.toFixed(0), (c) => c.maxTurns);
  renderTrend(); renderCompare(run); renderChips(run); renderTable(run);
}
$("f-plugin").addEventListener("change", (e) => { state.plugin = e.target.value; state.model = state.run = state.base = null; state.open.clear(); renderAll(); });
$("f-model").addEventListener("change", (e) => { state.model = e.target.value; state.run = state.base = null; renderAll(); });
$("f-run").addEventListener("change", (e) => { state.run = e.target.value; state.base = null; renderAll(); });
$("f-base").addEventListener("change", (e) => { state.base = e.target.value; renderCompare(current()); });
$("f-debug").addEventListener("change", (e) => { state.debug = e.target.checked; renderAll(); });
const THEMES = [["auto", null], ["light", "light"], ["dark", "dark"]];
let themeIdx = 0;
try { const saved = localStorage.getItem("pe-theme"); const i = THEMES.findIndex(([, v]) => v === saved); if (i > 0) themeIdx = i; } catch (e) {}
function applyTheme() {
  const v = THEMES[themeIdx][1];
  if (v) document.documentElement.dataset.theme = v; else delete document.documentElement.dataset.theme;
  $("theme").textContent = "Theme: " + THEMES[themeIdx][0];
  try { v ? localStorage.setItem("pe-theme", v) : localStorage.removeItem("pe-theme"); } catch (e) {}
}
$("theme").addEventListener("click", () => { themeIdx = (themeIdx + 1) % THEMES.length; applyTheme(); renderAll(); });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
let rT; addEventListener("resize", () => { clearTimeout(rT); rT = setTimeout(renderAll, 120); });
applyTheme(); renderAll();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
