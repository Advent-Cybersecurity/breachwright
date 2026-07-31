import unittest

from app.ai.output_validation import (
    MAX_AI_RECORDS,
    validate_ai_ad_paths,
    validate_ai_attack_paths,
    validate_ai_findings,
)


class AIOutputValidationTests(unittest.TestCase):
    def test_valid_finding_is_normalized(self):
        findings = validate_ai_findings(
            [
                {
                    "title": "  Missing security header  ",
                    "severity": "low",
                    "cvss_score": 3.1,
                }
            ]
        )

        self.assertEqual(findings[0].title, "Missing security header")
        self.assertEqual(findings[0].severity.value, "low")

    def test_invalid_finding_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid finding record 1"):
            validate_ai_findings(
                [{"title": "Invalid severity", "severity": "catastrophic"}]
            )

    def test_oversized_result_set_is_rejected(self):
        with self.assertRaisesRegex(ValueError, f"more than {MAX_AI_RECORDS}"):
            validate_ai_findings(
                [{"title": f"Finding {index}"} for index in range(MAX_AI_RECORDS + 1)]
            )

    def test_attack_path_requires_valid_risk_and_bounded_steps(self):
        with self.assertRaisesRegex(ValueError, "invalid attack path record 1"):
            validate_ai_attack_paths(
                [
                    {
                        "name": "Unbounded path",
                        "risk_level": "urgent",
                        "steps": [],
                    }
                ]
            )

        with self.assertRaisesRegex(ValueError, "invalid attack path record 1"):
            validate_ai_attack_paths(
                [
                    {
                        "name": "Too many steps",
                        "risk_level": "high",
                        "steps": [{}] * 1001,
                    }
                ]
            )

    def test_ad_nodes_are_bounded_and_normalized(self):
        paths = validate_ai_ad_paths(
            [
                {
                    "name": "  Privilege escalation  ",
                    "risk_level": "critical",
                    "path_nodes": [
                        {
                            "name": "HOST01",
                            "type": "computer",
                            "technique": "AdminTo",
                        }
                    ],
                }
            ]
        )
        self.assertEqual(paths[0].name, "Privilege escalation")
        self.assertEqual(paths[0].path_nodes[0].type, "computer")

        with self.assertRaisesRegex(
            ValueError,
            "invalid Active Directory path record 1",
        ):
            validate_ai_ad_paths(
                [
                    {
                        "name": "Invalid node",
                        "risk_level": "high",
                        "path_nodes": [{"name": "HOST01", "type": "x" * 51}],
                    }
                ]
            )


if __name__ == "__main__":
    unittest.main()
