import tempfile
import unittest
from pathlib import Path

from evalkit import aggregate, store
from evalkit.compare import bootstrap_ci, compare, verdict


def scores(**kw):
    return {k: {"score": v, "runs": [v], "stdev": 0.0, "errors": 0} for k, v in kw.items()}


class BootstrapTest(unittest.TestCase):
    def test_deterministic(self):
        d = [0.1, 0.2, -0.1, 0.3, 0.0]
        self.assertEqual(bootstrap_ci(d), bootstrap_ci(d))

    def test_clear_improvement_is_better(self):
        r = compare(scores(a=0.2, b=0.3, c=0.1, d=0.4, e=0.2, f=0.3),
                    scores(a=0.8, b=0.9, c=0.7, d=1.0, e=0.8, f=0.9), {})
        self.assertGreater(r["ci"][0], 0)
        self.assertEqual(r["verdict"], "better")

    def test_control_regression_blocks_better(self):
        r = compare(scores(a=0.2, b=0.2, c=0.2, ctl=1.0),
                    scores(a=0.9, b=0.9, c=0.9, ctl=0.67), {"ctl": ["control"]})
        self.assertEqual(r["control_regressions"], ["ctl"])
        self.assertNotEqual(r["verdict"], "better")

    def test_noise_is_not_proven(self):
        r = compare(scores(a=0.5, b=0.6, c=0.4), scores(a=0.6, b=0.5, c=0.4), {})
        self.assertEqual(r["verdict"], "inconclusive")

    def test_clear_regression_is_worse(self):
        self.assertEqual(verdict((-0.4, -0.1), []), "worse")

    def test_missing_cases_reported(self):
        r = compare(scores(a=1.0, old=1.0), scores(a=1.0, new=1.0), {})
        self.assertEqual((r["only_in_a"], r["only_in_b"]), (["old"], ["new"]))


class AggregateTest(unittest.TestCase):
    def test_case_scores(self):
        data = {"schemaVersion": 1, "costUsd": 1.5, "aggregates": {"overallScore": 0.75},
                "cases": [{"name": "x", "aggregates": {"score": 0.75},
                           "arms": {"with": [{"score": 1.0, "error": None},
                                             {"score": 0.5, "error": "timed out after 300s"}]}}]}
        s = aggregate.case_scores(data)["x"]
        self.assertEqual((s["score"], s["runs"], s["errors"]), (0.75, [1.0, 0.5], 1))
        self.assertEqual(aggregate.summary(data)["cost_usd"], 1.5)


class SuiteHashTest(unittest.TestCase):
    def test_changes_with_content(self):
        with tempfile.TemporaryDirectory() as t:
            case = Path(t) / "c1"
            case.mkdir()
            (case / "prompt.md").write_text("---\ntags: [control]\n---\nhi", encoding="utf-8")
            h1 = store.suite_hash([case])
            self.assertEqual(store.case_meta(case), {"name": "c1", "tags": ["control"]})
            (case / "prompt.md").write_text("---\ntags: [control]\n---\nhi!", encoding="utf-8")
            self.assertNotEqual(h1, store.suite_hash([case]))


if __name__ == "__main__":
    unittest.main()
