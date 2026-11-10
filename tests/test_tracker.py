import json
import tempfile
import unittest
from pathlib import Path

import yaml

from evalkit import store, tracker
from evalkit.config import ROOT


class TicketsTest(unittest.TestCase):
    def test_epic_sub_issues_exist(self):
        t = tracker.tickets()
        for n in t[300]["sub_issues"]:
            self.assertEqual(t[n]["parent"], 300)

    def test_linked_pages_exist(self):
        t, p = tracker.tickets(), tracker.pages()
        for ticket in t.values():
            for link in ticket.get("links") or []:
                self.assertIn(str(link["page_id"]), p)

    def test_jira_text_converts_only_known_numbers(self):
        self.assertEqual(tracker._jira_text("see #300, done in PR #58", [300]), "see DEMO-300, done in PR #58")


class RenderTest(unittest.TestCase):
    def test_github_fixture_per_issue(self):
        with tempfile.TemporaryDirectory() as d:
            tracker.render_github(Path(d))
            epic = json.loads((Path(d) / "fixtures/issues/300.json").read_text())
            self.assertEqual([s["number"] for s in epic["sub_issues"]], [301, 302, 303, 304, 305])
            self.assertIn("{{file:fixtures/issues/{input.issue_number}.json}}", (Path(d) / "issue_read.md").read_text())
            tools = json.loads((Path(d) / "_tools.json").read_text())["tools"]
            self.assertIn("issue_read", [t["name"] for t in tools])

    def test_jira_fixtures_cover_every_page_tool(self):
        with tempfile.TemporaryDirectory() as d:
            tracker.render_jira(Path(d))
            fx = Path(d) / "fixtures"
            for pid in tracker.pages():
                for sub in ("pages", "children", "comments-footer", "comments-inline"):
                    self.assertTrue((fx / sub / f"{pid}.json").is_file(), f"{sub}/{pid}")
            issue = json.loads((fx / "issues/DEMO-300.json").read_text())
            self.assertIn("DEMO-301", issue["fields"]["description"])
            self.assertEqual(len(issue["fields"]["subtasks"]), 5)
            forbidden = json.loads((fx / "pages/5599.json").read_text())
            self.assertEqual(forbidden["statusCode"], 403)
            link = json.loads((fx / "links/DEMO-207.json").read_text())
            self.assertTrue(link[0]["object"]["url"].endswith("/pages/5502"))


class SuitesTest(unittest.TestCase):
    """Кожен кейс завантажується: є prompt, грейдери з типом, fixture з відомим профілем."""

    def test_cases_are_well_formed(self):
        n = 0
        for plugin_dir in (ROOT / "suites").iterdir():
            for case in store.case_dirs(plugin_dir / "cases"):
                n += 1
                front = store.read_frontmatter(case / "prompt.md")
                self.assertTrue(front.get("tags"), case)
                graders = list((case / "graders").glob("*.md"))
                self.assertTrue(graders, case)
                for g in graders:
                    self.assertIn("type", store.read_frontmatter(g), g)
                fx = yaml.safe_load((case / "fixture.yaml").read_text())
                self.assertIn(fx["profile"], ("dev", "qa"), case)
                if fx.get("preset"):
                    self.assertTrue((tracker.TRACKER / "presets" / fx["preset"]).is_dir(), case)
        self.assertGreaterEqual(n, 20)

    def test_build_writes_case_yaml_and_scaffold(self):
        case = ROOT / "suites/qa-docs/cases/qd-export-verified"
        with tempfile.TemporaryDirectory() as d:
            plugin = Path(d) / "plugin"
            plugin.mkdir()
            (plugin / ".mcp.json").write_text('{"mcpServers": {"jira": {"type": "http"}}}')
            out = Path(d) / "evals"
            self.assertEqual(tracker.build(plugin, [case], out, "/m2"), ["jira"])
            built = out / case.name
            self.assertEqual(yaml.safe_load((built / "case.yaml").read_text())["context"]["scaffold_script"], "scaffold.sh")
            script = (built / "scaffold.sh").read_text()
            self.assertIn("QA_DOCS_CONFLUENCE_PARENT=777001", script)
            self.assertIn("qa-docs/domains/booking-cancellation", script)
            self.assertFalse((built / "fixture.yaml").exists())


if __name__ == "__main__":
    unittest.main()
