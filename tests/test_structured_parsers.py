import json
from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.correlation.structured_parsers import parse_structured


class StructuredInterchangeParserTests(unittest.TestCase):
    def test_nuclei_jsonl_preserves_template_and_target(self):
        records = parse_structured(
            json.dumps({
                "template-id": "CVE-2024-0001-check",
                "host": "example.test",
                "matched-at": "https://example.test/path",
                "info": {"name": "Example issue", "severity": "high"},
            }),
            "nuclei",
        )
        self.assertEqual(records[0]["host"], "example.test")
        self.assertEqual(records[0]["vulns"][0]["port"], 443)
        self.assertEqual(records[0]["vulns"][0]["plugin_id"], "CVE-2024-0001-check")
        self.assertEqual(records[0]["vulns"][0]["cve"], "CVE-2024-0001")

    def test_malformed_nuclei_metadata_is_safely_normalized(self):
        records = parse_structured(
            json.dumps({
                "template-id": {"unexpected": "object"},
                "host": "https://[broken-ipv6",
                "port": "not-a-port",
                "matched-at": "https://[broken-ipv6/path",
                "info": {
                    "name": {"unexpected": "object"},
                    "severity": ["high"],
                    "description": ["unexpected"],
                },
            }),
            "nuclei",
        )
        self.assertEqual(records[0]["host"], "https://[broken-ipv6")
        finding = records[0]["vulns"][0]
        self.assertIsNone(finding["port"])
        self.assertEqual(finding["severity"], "info")
        self.assertIsInstance(finding["title"], str)

    def test_sarif_21_rule_metadata_and_location_are_normalized(self):
        document = {
            "version": "2.1.0",
            "runs": [{
                "tool": {"driver": {"name": "Example Scanner", "rules": [{
                    "id": "CVE-2025-1234",
                    "shortDescription": {"text": "Unsafe endpoint"},
                    "help": {"text": "Restrict the endpoint."},
                    "properties": {"security-severity": "8.2"},
                }]}},
                "results": [{
                    "ruleId": "CVE-2025-1234",
                    "message": {"text": "The endpoint is exposed."},
                    "locations": [{"physicalLocation": {"artifactLocation": {"uri": "https://example.test:8443/admin"}}}],
                }],
            }],
        }
        records = parse_structured(json.dumps(document), "sarif")
        self.assertEqual(records[0]["host"], "example.test")
        finding = records[0]["vulns"][0]
        self.assertEqual(finding["port"], 8443)
        self.assertEqual(finding["severity"], "high")
        self.assertEqual(finding["cve"], "CVE-2025-1234")
        self.assertEqual(finding["solution"], "Restrict the endpoint.")

    def test_invalid_sarif_is_rejected_without_partial_records(self):
        self.assertEqual(parse_structured("not json", "sarif"), [])
        self.assertEqual(parse_structured(json.dumps({"runs": "bad"}), "sarif"), [])

    def test_malformed_sarif_nested_metadata_does_not_crash_upload(self):
        document = {
            "version": "2.1.0",
            "runs": [{
                "tool": "invalid",
                "results": [{
                    "ruleId": "example-rule",
                    "message": {"text": "A usable result with malformed metadata."},
                    "properties": "invalid",
                    "locations": ["invalid"],
                }],
            }],
        }
        records = parse_structured(json.dumps(document), "sarif")
        self.assertEqual(records[0]["host"], "unknown")
        self.assertEqual(records[0]["vulns"][0]["plugin_id"], "example-rule")


if __name__ == "__main__":
    unittest.main()
