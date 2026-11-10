"""Тестовий трекер: спільні тікети -> моки MCP-серверів плагіна + scaffold робочого простору.

Джерело правди:
  tracker/tickets/<n>.yaml      тікет (номер n; у Jira це DEMO-<n>)
  tracker/pages/<id>.yaml       сторінка Confluence
  tracker/workspace/booking-core/  синтетичний Maven-проєкт, на який посилаються тікети
  tracker/presets/<domain>/     готовий домен qa-docs для кейсів експорту

build() кладе в теку кейсів робочої копії плагіна:
  mocks/github/...   якщо плагін оголошує MCP-сервер `github` (java-developer, java-analyst)
  mocks/jira/...     якщо оголошує `jira` (qa-docs: Jira + Confluence)
  <case>/case.yaml + <case>/scaffold.sh   для кожного кейсу з fixture.yaml

Інструменти без мок-файлу плагіну недоступні, тож справжній трекер не зачіпається.

    python -m evalkit.tracker preview --plugin qa-docs   # зібрати в тимчасову теку і показати дерево
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from .config import ROOT

TRACKER = ROOT / "tracker"
GH_OWNER, GH_REPO = "demo-org", "booking-core"
JIRA_PROJECT, JIRA_SITE, CLOUD_ID = "DEMO", "demo.atlassian.net", "4f1c9a2e-0d3b-4e7a-9b61-5a2c8d7e1f00"
QA_SPACE, QA_PARENT = "QA", "777001"
# Фіксовані дати комітів дають однаковий SHA при кожному scaffold.
GIT_DATE = "2026-10-30T12:00:00+00:00"


# ---------- завантаження ----------

def _load_dir(d: Path) -> List[Dict[str, Any]]:
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.yaml"))]


def tickets() -> Dict[int, Dict[str, Any]]:
    return {int(t["number"]): t for t in _load_dir(TRACKER / "tickets")}


def pages() -> Dict[str, Dict[str, Any]]:
    return {str(p["id"]): p for p in _load_dir(TRACKER / "pages")}


def _iso(v: Any) -> str:
    return v.isoformat().replace("+00:00", "Z") if hasattr(v, "isoformat") else str(v)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _mock(path: Path, body: str, front: Dict[str, Any] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + "---\n" if front else ""
    path.write_text(head + body.rstrip() + "\n", encoding="utf-8")


def _tools_json(path: Path, tools: List[Dict[str, Any]]) -> None:
    _write_json(path, {"tools": tools})


def _schema(props: Dict[str, Any], required: Iterable[str]) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(required)}


S = {"type": "string"}
N = {"type": "number"}


# ---------- GitHub (java-developer, java-analyst) ----------

def _gh_issue(t: Dict[str, Any], all_t: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    out = {
        "number": t["number"],
        "title": t["title"],
        "state": t["state"],
        "html_url": f"https://github.com/{GH_OWNER}/{GH_REPO}/issues/{t['number']}",
        "user": {"login": t["author"]},
        "labels": [{"name": l} for l in t.get("labels", [])],
        "created_at": _iso(t["created"]),
        "body": t["body"],
        "comments": [{"user": {"login": c["author"]}, "created_at": _iso(c["created"]), "body": c["body"]}
                     for c in t.get("comments") or []],
    }
    if t.get("sub_issues"):
        out["sub_issues"] = [{"number": n, "title": all_t[n]["title"], "state": all_t[n]["state"]}
                             for n in t["sub_issues"]]
    if t.get("parent"):
        p = all_t[t["parent"]]
        out["parent"] = {"number": p["number"], "title": p["title"], "state": p["state"]}
    return out


def render_github(dst: Path) -> None:
    all_t = tickets()
    for n, t in all_t.items():
        _write_json(dst / "fixtures" / "issues" / f"{n}.json", _gh_issue(t, all_t))
    listing = {"total_count": len(all_t), "items": [
        {"number": n, "title": t["title"], "state": t["state"], "labels": [{"name": l} for l in t.get("labels", [])],
         "html_url": f"https://github.com/{GH_OWNER}/{GH_REPO}/issues/{n}"} for n, t in all_t.items()]}

    # Один файл на issue незалежно від method: опис, коментарі, під-задачі й батьківська задача разом.
    _mock(dst / "issue_read.md", "{{file:fixtures/issues/{input.issue_number}.json}}",
          {"expect": {"owner": GH_OWNER, "repo": GH_REPO, "issue_number": "number",
                      "method": ["get", "get_comments", "get_sub_issues", "get_parent", "get_labels"]}})
    body = json.dumps(listing, indent=2, ensure_ascii=False)
    _mock(dst / "search_issues.md", body, {"expect": {"query": "string"}})
    _mock(dst / "list_issues.md", body, {"expect": {"owner": GH_OWNER, "repo": GH_REPO}})
    _tools_json(dst / "_tools.json", [
        {"name": "issue_read",
         "description": "Get information about a specific issue in a GitHub repository. method: get (details), "
                        "get_comments, get_sub_issues, get_parent, get_labels.",
         "inputSchema": _schema({"owner": S, "repo": S, "issue_number": N,
                                 "method": {"type": "string", "enum": ["get", "get_comments", "get_sub_issues",
                                                                       "get_parent", "get_labels"]},
                                 "page": N, "perPage": N}, ["owner", "repo", "issue_number", "method"])},
        {"name": "search_issues",
         "description": "Search for issues in GitHub repositories using issues search syntax.",
         "inputSchema": _schema({"query": S, "owner": S, "repo": S, "sort": S, "order": S, "page": N, "perPage": N},
                                ["query"])},
        {"name": "list_issues",
         "description": "List issues in a GitHub repository.",
         "inputSchema": _schema({"owner": S, "repo": S, "state": S, "labels": {"type": "array", "items": S},
                                 "since": S, "perPage": N, "after": S}, ["owner", "repo"])},
    ])


# ---------- Jira + Confluence (qa-docs) ----------

def _jira_text(text: str, numbers: Iterable[int]) -> str:
    """#205 -> DEMO-205 лише для номерів, які є в трекері (PR #58 лишається як є)."""
    known = set(numbers)
    return re.sub(r"(?<![\w/])#(\d+)\b",
                  lambda m: f"{JIRA_PROJECT}-{m.group(1)}" if int(m.group(1)) in known else m.group(0), text)


_JIRA_TYPE = {"bug": "Bug", "story": "Story", "epic": "Epic", "task": "Sub-task"}


def _page_url(pid: str, space: str = "PROD") -> str:
    return f"https://{JIRA_SITE}/wiki/spaces/{space}/pages/{pid}"


def _jira_issue(t: Dict[str, Any], all_t: Dict[int, Dict[str, Any]], all_p: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    nums = all_t.keys()
    key = f"{JIRA_PROJECT}-{t['number']}"
    desc = _jira_text(t["body"], nums)
    for link in t.get("links") or []:
        p = all_p.get(str(link["page_id"]), {})
        desc += f"\n\nConfluence: [{link['title']}]({_page_url(link['page_id'], p.get('space', 'PROD'))})"
    comments = t.get("comments") or []
    fields: Dict[str, Any] = {
        "summary": t["title"],
        "description": desc,
        "status": {"name": "Done" if t["state"] == "closed" else "To Do"},
        "issuetype": {"name": _JIRA_TYPE.get(t["type"], "Task")},
        "priority": {"name": "Medium"},
        "labels": t.get("labels", []),
        "project": {"key": JIRA_PROJECT, "name": "Demo Booking"},
        "reporter": {"displayName": t["author"]},
        "created": _iso(t["created"]),
        "updated": _iso(comments[-1]["created"]) if comments else _iso(t["created"]),
        "resolution": {"name": "Done"} if t["state"] == "closed" else None,
        "comment": {"total": len(comments), "comments": [
            {"id": str(10000 + i), "author": {"displayName": c["author"]}, "created": _iso(c["created"]),
             "body": _jira_text(c["body"], nums)} for i, c in enumerate(comments, 1)]},
    }
    if t.get("sub_issues"):
        fields["subtasks"] = [{"key": f"{JIRA_PROJECT}-{n}", "fields": {
            "summary": all_t[n]["title"], "status": {"name": "To Do"}}} for n in t["sub_issues"]]
    if t.get("parent"):
        p = all_t[t["parent"]]
        fields["parent"] = {"key": f"{JIRA_PROJECT}-{p['number']}", "fields": {"summary": p["title"]}}
    return {"key": key, "id": str(10000 + t["number"]),
            "self": f"https://{JIRA_SITE}/rest/api/3/issue/{10000 + t['number']}", "fields": fields}


def render_jira(dst: Path) -> None:
    all_t, all_p = tickets(), pages()
    fx = dst / "fixtures"
    for n, t in all_t.items():
        key = f"{JIRA_PROJECT}-{n}"
        _write_json(fx / "issues" / f"{key}.json", _jira_issue(t, all_t, all_p))
        _write_json(fx / "links" / f"{key}.json", [
            {"id": i, "object": {"url": _page_url(l["page_id"], all_p.get(str(l["page_id"]), {}).get("space", "PROD")),
                                 "title": l["title"]}}
            for i, l in enumerate(t.get("links") or [], 1)])
    for pid, p in all_p.items():
        if p.get("forbidden"):
            denied = {"error": "Forbidden", "statusCode": 403,
                      "message": f"You do not have permission to view page {pid} or it does not exist."}
            for sub in ("pages", "children", "comments-footer", "comments-inline"):
                _write_json(fx / sub / f"{pid}.json", denied)
            continue
        _write_json(fx / "pages" / f"{pid}.json", {
            "id": pid, "title": p["title"], "type": "page", "status": "current", "spaceId": p["space"],
            "parentId": p.get("parent"), "version": {"number": 3, "createdAt": _iso(p["updated"]),
                                                     "authorId": p.get("author")},
            "body": p["body"], "_links": {"webui": _page_url(pid, p["space"])}})
        _write_json(fx / "children" / f"{pid}.json", {"results": [
            {"id": c, "title": all_p[c]["title"], "type": "page", "depth": 1} for c in p.get("children") or []]})
        _write_json(fx / "comments-footer" / f"{pid}.json", {"results": [
            {"id": f"c{pid}{i}", "author": c["author"], "createdAt": _iso(c["created"]), "body": c["body"]}
            for i, c in enumerate(p.get("comments") or [], 1)]})
        _write_json(fx / "comments-inline" / f"{pid}.json", {"results": []})

    cloud = {"cloudId": "string"}
    _mock(dst / "getAccessibleAtlassianResources.md", json.dumps(
        [{"id": CLOUD_ID, "url": f"https://{JIRA_SITE}", "name": "demo", "scopes": ["read:jira-work", "read:confluence-content.all", "write:confluence-content"]}], indent=2))
    _mock(dst / "atlassianUserInfo.md", json.dumps(
        {"account_id": "qa-engineer-1", "name": "qa-engineer", "email": "qa-engineer@demo.example"}, indent=2))
    _mock(dst / "getJiraIssue.md", "{{file:fixtures/issues/{input.issueIdOrKey}.json}}",
          {"expect": {**cloud, "issueIdOrKey": "/^DEMO-\\d+$/"}})
    _mock(dst / "getJiraIssueRemoteIssueLinks.md", "{{file:fixtures/links/{input.issueIdOrKey}.json}}",
          {"expect": {**cloud, "issueIdOrKey": "/^DEMO-\\d+$/"}})
    # JQL не інтерпретується: пошук завжди повертає весь проєкт DEMO, від новіших до старших.
    search = {"isLast": True, "issues": [
        {"key": f"{JIRA_PROJECT}-{n}", "fields": {"summary": t["title"],
                                                  "status": {"name": "Done" if t["state"] == "closed" else "To Do"},
                                                  "issuetype": {"name": _JIRA_TYPE.get(t["type"], "Task")},
                                                  "labels": t.get("labels", []), "created": _iso(t["created"])}}
        for n, t in sorted(all_t.items(), key=lambda kv: _iso(kv[1]["created"]), reverse=True)]}
    _mock(dst / "searchJiraIssuesUsingJql.md", json.dumps(search, indent=2, ensure_ascii=False),
          {"expect": {**cloud, "jql": "string"}})
    cql = {"results": [{"content": {"id": pid, "type": "page", "title": p["title"]}, "url": _page_url(pid, p["space"]),
                        "lastModified": _iso(p["updated"])}
                       for pid, p in all_p.items() if not p.get("forbidden") and p["space"] == "PROD"]}
    _mock(dst / "searchConfluenceUsingCql.md", json.dumps(cql, indent=2, ensure_ascii=False),
          {"expect": {**cloud, "cql": "string"}})
    for tool, sub in (("getConfluencePage", "pages"), ("getConfluencePageDescendants", "children"),
                      ("getConfluencePageFooterComments", "comments-footer"),
                      ("getConfluencePageInlineComments", "comments-inline")):
        _mock(dst / f"{tool}.md", f"{{{{file:fixtures/{sub}/{{input.pageId}}.json}}}}",
              {"expect": {**cloud, "pageId": "/^\\d+$/"}})
    _mock(dst / "createConfluencePage.md", json.dumps(
        {"id": "900123", "title": "{{input.title}}", "status": "current", "spaceId": "{{input.spaceId}}",
         "parentId": "{{input.parentId}}", "version": {"number": 1},
         "_links": {"webui": f"https://{JIRA_SITE}/wiki/spaces/{QA_SPACE}/pages/900123"}}, indent=2),
          {"expect": {**cloud, "spaceId": "string", "parentId": "string", "title": "string", "body": "string"}})
    _mock(dst / "updateConfluencePage.md", json.dumps(
        {"id": "{{input.pageId}}", "title": "{{input.title}}", "status": "current", "version": {"number": 2},
         "_links": {"webui": f"https://{JIRA_SITE}/wiki/spaces/{QA_SPACE}/pages/" + "{{input.pageId}}"}}, indent=2),
          {"expect": {**cloud, "pageId": "string", "body": "string"}})

    c = {"cloudId": {"type": "string", "description": "Cloud ID (UUID or site URL)"}}
    fmt = {"type": "string", "enum": ["markdown", "adf"]}
    page_fmt = {"type": "string", "enum": ["html", "markdown", "adf"]}
    key = {"type": "string", "description": "Issue ID or key (e.g., PROJ-123 or 10000)"}
    pid = {"type": "string", "description": "Page or blog post ID"}
    _tools_json(dst / "_tools.json", [
        {"name": "getAccessibleAtlassianResources", "description": "Get cloudId to make tool calls.",
         "inputSchema": _schema({}, [])},
        {"name": "atlassianUserInfo", "description": "Get current user info", "inputSchema": _schema({}, [])},
        {"name": "getJiraIssue", "description": "Get issue details.",
         "inputSchema": _schema({**c, "issueIdOrKey": key, "fields": {"type": "array", "items": S},
                                 "expand": S, "responseContentFormat": fmt}, ["cloudId", "issueIdOrKey"])},
        {"name": "getJiraIssueRemoteIssueLinks", "description": "Get remote links",
         "inputSchema": _schema({**c, "issueIdOrKey": key, "globalId": S}, ["cloudId", "issueIdOrKey"])},
        {"name": "searchJiraIssuesUsingJql", "description": "Search issues with JQL.",
         "inputSchema": _schema({**c, "jql": {"type": "string", "description": "JQL query"},
                                 "fields": {"type": "array", "items": S}, "maxResults": N, "nextPageToken": S,
                                 "responseContentFormat": fmt}, ["cloudId", "jql"])},
        {"name": "searchConfluenceUsingCql", "description": "Search Confluence content using CQL.",
         "inputSchema": _schema({**c, "cql": S, "cqlcontext": S, "limit": N, "cursor": S}, ["cloudId", "cql"])},
        {"name": "getConfluencePage", "description": "Get a Confluence page by ID, including body content.",
         "inputSchema": _schema({**c, "pageId": pid, "contentFormat": page_fmt,
                                 "contentType": {"type": "string", "enum": ["page", "blog"]}}, ["cloudId", "pageId"])},
        {"name": "getConfluencePageDescendants", "description": "Get child pages of specified page",
         "inputSchema": _schema({**c, "pageId": pid, "depth": N, "limit": N, "cursor": S}, ["cloudId", "pageId"])},
        {"name": "getConfluencePageFooterComments", "description": "Get footer comments for a page",
         "inputSchema": _schema({**c, "pageId": pid, "contentFormat": fmt, "limit": N}, ["cloudId", "pageId"])},
        {"name": "getConfluencePageInlineComments", "description": "Get inline comments for a page",
         "inputSchema": _schema({**c, "pageId": pid, "contentFormat": fmt, "limit": N}, ["cloudId", "pageId"])},
        {"name": "createConfluencePage", "description": "Create a new Confluence page.",
         "inputSchema": _schema({**c, "spaceId": S, "parentId": S, "title": S, "body": S, "contentFormat": page_fmt,
                                 "contentType": {"type": "string", "enum": ["page", "blog"]}},
                                ["cloudId", "spaceId", "title", "body"])},
        {"name": "updateConfluencePage", "description": "Update an existing Confluence page.",
         "inputSchema": _schema({**c, "pageId": S, "title": S, "body": S, "contentFormat": page_fmt,
                                 "versionMessage": S, "parentId": S, "spaceId": S}, ["cloudId", "pageId", "body"])},
    ])


# ---------- scaffold ----------

def _targz_b64(src: Path, exclude: Iterable[str] = ("target", ".mvn")) -> str:
    buf = io.BytesIO()
    skip = set(exclude)
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tar:
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(src)
            if rel.parts[0] in skip or not p.is_file():
                continue
            info = tar.gettarinfo(str(p), arcname=rel.as_posix())
            info.mtime, info.uid, info.gid, info.uname, info.gname = 1793000000, 0, 0, "", ""
            with p.open("rb") as f:
                tar.addfile(info, f)
    return base64.b64encode(buf.getvalue()).decode()


def _wrap(b64: str, width: int = 76) -> str:
    return "\n".join(b64[i:i + width] for i in range(0, len(b64), width))


_HEADER = """#!/usr/bin/env bash
# Generated by evalkit.tracker. Builds the workspace for one eval run. Do not edit by hand.
set -euo pipefail
export GIT_AUTHOR_DATE='{date}' GIT_COMMITTER_DATE='{date}'
g() {{ git -c user.name=demo-dev -c user.email=dev@demo.example -c init.defaultBranch=main -c commit.gpgsign=false "$@"; }}
unpack() {{ mkdir -p "$1"; base64 --decode | tar -xzf - -C "$1"; }}
new_repo() {{  # <dir> <remote>
  ( cd "$1" && g init -q && g add -A && g commit -qm "Import booking-core 1.4.0" && g remote add origin "$2" )
}}
"""


def scaffold_script(fixture: Dict[str, Any], maven_repo: str) -> str:
    profile = fixture.get("profile", "dev")
    repo_b64 = _wrap(_targz_b64(TRACKER / "workspace" / "booking-core"))
    remote = f"https://github.com/{GH_OWNER}/{GH_REPO}.git"
    mvn_cfg = f"printf -- '-o\\n-Dmaven.repo.local=%s\\n' '{maven_repo}' > \"$1/.mvn/maven.config\""
    out = [_HEADER.format(date=GIT_DATE)]
    out.append(f"mvn_offline() {{ mkdir -p \"$1/.mvn\"; {mvn_cfg}; }}\n")
    if profile == "dev":
        # java-developer / java-analyst: Claude стартує в корені репозиторію booking-core.
        out.append(f"unpack . <<'B64'\n{repo_b64}\nB64\n")
        out.append(f"mvn_offline .\nnew_repo . {remote}\n")
    elif profile == "qa":
        # qa-docs: Claude стартує в корені робочого простору сервера; репозиторії - його підтеки.
        out.append(f"unpack booking-core <<'B64'\n{repo_b64}\nB64\n")
        out.append(f"mvn_offline booking-core\nnew_repo booking-core {remote}\n")
        out.append(_QA_WORKSPACE.format(space=QA_SPACE, parent=QA_PARENT, site=JIRA_SITE))
        preset = fixture.get("preset")
        if preset:
            status = fixture.get("status", "verified")
            line = "verified by qa-lead on 2026-11-02" if status in ("verified", "exported") else "draft"
            out.append(f"unpack qa-docs/domains/{preset} <<'B64'\n{_wrap(_targz_b64(TRACKER / 'presets' / preset))}\nB64\n")
            out.append(_PRESET_FILL.format(slug=preset, status=status, line=line,
                                           vat="2026-11-02" if line != "draft" else "",
                                           vby="qa-lead" if line != "draft" else ""))
    else:
        raise SystemExit(f"fixture.yaml: невідомий profile '{profile}' (dev | qa)")
    return "".join(out)


_QA_WORKSPACE = """mkdir -p .qa-docs qa-docs/domains
cat > .qa-docs/config.env <<'EOF'
QA_DOCS_LANGUAGE=English
QA_DOCS_MAIN_PROJECT=booking-core
QA_DOCS_CONFLUENCE_CLOUD={site}
QA_DOCS_CONFLUENCE_SPACE={space}
QA_DOCS_CONFLUENCE_SPACE_ID=
QA_DOCS_CONFLUENCE_PARENT={parent}
QA_DOCS_STALE_HOURS=48
QA_DOCS_MAX_SUBFLOWS=3
EOF
sha="$(git -C booking-core rev-parse HEAD)"
printf 'repo\\tbranch\\tcommit\\tcommit_date\\tupdated_at\\tstatus\\n' > .qa-docs/sources.tsv
printf 'booking-core\\tmain\\t%s\\t%s\\t%s\\tok\\n' "$sha" "$GIT_COMMITTER_DATE" "$(date +%s)" >> .qa-docs/sources.tsv
cat > qa-docs/modules.md <<'EOF'
# Module map

Source repositories of the workspace and how they connect.

Updated: 2026-11-01 by qa-lead

## Repositories

| Repository | Kind | Role in the product | Talks to |
| --- | --- | --- | --- |
| `booking-core` | maven | Rates, discounts, bookings, cancellations, partner notifications | partners (email) |
EOF
cat > qa-docs/domains.md <<'EOF'
# Domain map

Updated: 2026-11-01 by qa-lead

| Domain | Slug | What it covers | Repositories | Entry points | Document |
| --- | --- | --- | --- | --- | --- |
EOF
"""

_PRESET_FILL = """short="$(git -C booking-core rev-parse --short=12 HEAD)"
today="$(date +%Y-%m-%d)"
for f in qa-docs/domains/{slug}/*; do
  sed -i.bak -e "s/__COMMIT__/$short/g" -e "s/__TODAY__/$today/g" -e "s/__STATUS__/{status}/g" \\
    -e "s/__STATUS_LINE__/{line}/g" -e "s/__VERIFIED_AT__/{vat}/g" -e "s/__VERIFIED_BY__/{vby}/g" "$f"
  rm -f "$f.bak"
done
echo '| Booking cancellation and refunds | `{slug}` | Cancelling a booking, refunds, partner notice | booking-core | BookingService.cancel | domains/{slug}/domain.md |' >> qa-docs/domains.md
"""


# ---------- збірка в теку кейсів ----------

def plugin_servers(plugin_dir: Path) -> List[str]:
    f = plugin_dir / ".mcp.json"
    return sorted((json.loads(f.read_text(encoding="utf-8")).get("mcpServers") or {}).keys()) if f.is_file() else []


def build(plugin_dir: Path, case_dirs: List[Path], target: Path, maven_repo: str) -> List[str]:
    """Копіює кейси в target, додає scaffold і моки. Повертає список змоканих серверів."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for d in case_dirs:
        dst = target / d.name
        shutil.copytree(d, dst)
        fx = dst / "fixture.yaml"
        if fx.is_file():
            fixture = yaml.safe_load(fx.read_text(encoding="utf-8")) or {}
            (dst / "scaffold.sh").write_text(scaffold_script(fixture, maven_repo), encoding="utf-8")
            (dst / "scaffold.sh").chmod(0o755)
            case = {"schema_version": "1.1", "name": d.name, "context": {"scaffold_script": "scaffold.sh"}}
            (dst / "case.yaml").write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
            fx.unlink()
    servers = plugin_servers(plugin_dir)
    mocked = []
    if "github" in servers:
        render_github(target / "mocks" / "github")
        mocked.append("github")
    if "jira" in servers:
        render_jira(target / "mocks" / "jira")
        mocked.append("jira")
    return mocked


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("preview", help="зібрати кейси плагіна в тимчасову теку")
    pv.add_argument("--plugin", required=True)
    pv.add_argument("--out", help="куди зібрати (за замовчуванням тимчасова тека)")
    args = p.parse_args(argv)

    from . import config, store
    cfg = config.load()
    plug = cfg.plugin(args.plugin)
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix=f"pe-preview-{args.plugin}-"))
    dirs = store.case_dirs(ROOT / "suites" / args.plugin / "cases")
    mocked = build(plug.local_dir, dirs, out, cfg.maven_repo)
    print(f"{len(dirs)} кейсів, моки: {', '.join(mocked) or 'немає'} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
