import os
import sys
import unittest
from datetime import date
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.engagements.models import Severity
from app.reports.content import build_report_content


class ReportContentTests(unittest.TestCase):
    def test_report_contains_engagement_findings_and_brand_attribution(self):
        engagement = SimpleNamespace(
            name="External Assessment",
            client_name="Example Client",
            scope="example.test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 15),
        )
        finding = SimpleNamespace(
            title="Outdated service",
            severity=Severity.high,
            cvss_score=8.1,
            affected_hosts="10.0.0.5",
            retest_status="open",
            description="A service requires an update.",
            evidence="Version response captured.",
            remediation="Install the supported release.",
        )
        attack_path = SimpleNamespace(
            name="External foothold",
            risk_level="high",
            description="The exposed service permits initial access.",
        )

        report = build_report_content(engagement, [finding], [attack_path])

        self.assertIn("External Assessment - Penetration Test Report", report)
        self.assertIn("created by Advent Cybersecurity", report)
        self.assertIn("| High | 1 |", report)
        self.assertIn("Outdated service", report)
        self.assertIn("Install the supported release.", report)
        self.assertIn("External foothold", report)

    def test_empty_engagement_still_produces_complete_report(self):
        engagement = SimpleNamespace(
            name="Empty Assessment",
            client_name="Example Client",
            scope=None,
            start_date=None,
            end_date=None,
        )

        report = build_report_content(engagement, [], [])

        self.assertIn("No findings were recorded", report)
        self.assertIn("No attack paths were recorded", report)
        self.assertIn("## Conclusion", report)


if __name__ == "__main__":
    unittest.main()
