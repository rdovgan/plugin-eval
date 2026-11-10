import json
import unittest

from evalkit import html_report


class HtmlReportTest(unittest.TestCase):
    def test_render_embeds_data_safely(self):
        data = {"generated": "2026-11-10T00:00", "runs": [{"key": "k", "cases": [
            {"name": "x", "prompt": "</script><script>alert(1)</script>"}]}]}
        html = html_report.render(data)
        self.assertNotIn("</script><script>alert(1)", html)
        start = html.index('type="application/json">') + len('type="application/json">')
        payload = html[start:html.index("</script>", start)]
        self.assertEqual(json.loads(payload), data)

    def test_collect_marks_ungraded_runs(self):
        for run in html_report.collect()["runs"]:
            ungraded = sum(a["ungraded"] for c in run["cases"] for a in c["attempts"])
            self.assertEqual(run["ungraded"], ungraded)
            if ungraded:
                self.assertTrue(run["partial"])


if __name__ == "__main__":
    unittest.main()
