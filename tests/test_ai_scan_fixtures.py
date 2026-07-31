from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.correlation.engine import correlate, to_ai_prompt
from app.correlation.structured_parsers import parse_structured
from app.findings.dedup import should_update_finding


FIXTURES = Path(__file__).parent / "fixtures" / "ai_eval"


class AIScanFixtureTests(unittest.TestCase):
    def _parse(self, filename: str, scan_type: str, scan_id: str):
        records = parse_structured(
            (FIXTURES / filename).read_text(encoding="utf-8"),
            scan_type,
        )
        for record in records:
            record["_scan_id"] = scan_id
            record["_scan_filename"] = filename
            record["_scan_type"] = scan_type
            for vulnerability in record.get("vulns", []):
                vulnerability["_scan_id"] = scan_id
                vulnerability["_scan_filename"] = filename
                vulnerability["_scan_type"] = scan_type
        return records

    def test_sanitized_scans_produce_stable_grounded_evidence(self):
        correlated = correlate(
            {
                "nmap": self._parse("nmap_smb.xml", "nmap", "scan-nmap"),
                "nessus": self._parse("nessus_tls.nessus", "nessus", "scan-nessus"),
                "burp": self._parse("burp_xss.xml", "burp", "scan-burp"),
            }
        )
        titles = {finding["title"] for finding in correlated["findings"]}
        self.assertIn("SMB Signing Not Required", titles)
        self.assertIn("TLS Version 1.0 Protocol Detection", titles)
        self.assertIn("Reflected cross-site scripting", titles)
        all_refs = [
            ref
            for finding in correlated["findings"]
            for ref in finding["evidence_refs"]
        ]
        self.assertTrue(all(ref["id"].startswith("CF-") for ref in all_refs))
        self.assertEqual(
            {ref["scan_id"] for ref in all_refs},
            {"scan-nmap", "scan-nessus", "scan-burp"},
        )
        prompt = to_ai_prompt(correlated)
        for ref in all_refs:
            self.assertIn(ref["id"], prompt)
            self.assertIn(ref["filename"], prompt)

    def test_zero_cvss_survives_correlation_prompt_and_deduplication(self):
        correlated = correlate({
            "example": [{
                "host": "example.test",
                "hostnames": [],
                "ports": [],
                "vulns": [{
                    "title": "Informational observation",
                    "severity": "info",
                    "cvss": 0.0,
                    "description": "A valid zero-score observation.",
                    "source": "example",
                }],
            }],
        })
        finding = correlated["findings"][0]
        self.assertEqual(finding["cvss"], 0.0)
        self.assertIn("CVSS: 0.0", to_ai_prompt(correlated))
        self.assertEqual(
            should_update_finding(
                {"cvss_score": None},
                {"cvss_score": 0.0},
            )["cvss_score"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
