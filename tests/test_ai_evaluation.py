import json
from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ai.evaluation import evaluate_findings, meets_release_baseline


FIXTURE = Path(__file__).parent / "fixtures" / "ai_eval" / "sanitized_cases.json"


class AIEvaluationTests(unittest.TestCase):
    def test_sanitized_baseline_cases_meet_release_thresholds(self):
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(case=case["name"]):
                metrics = evaluate_findings(
                    case["expected"],
                    case["actual"],
                    set(case["allowed_evidence_ids"]),
                )
                self.assertTrue(meets_release_baseline(metrics), metrics.as_dict())

    def test_false_positive_and_unknown_evidence_fail_baseline(self):
        metrics = evaluate_findings(
            [],
            [
                {
                    "title": "Invented critical issue",
                    "severity": "critical",
                    "affected_hosts": "10.0.0.99",
                    "evidence_refs": ["MADE-UP"],
                }
            ],
            {"RAW-0001-E001"},
        )
        self.assertEqual(metrics.false_positives, 1)
        self.assertEqual(metrics.grounded_rate, 0)
        self.assertFalse(meets_release_baseline(metrics))


if __name__ == "__main__":
    unittest.main()
