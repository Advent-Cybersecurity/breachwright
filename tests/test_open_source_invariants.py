from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OpenSourceReleaseTests(unittest.TestCase):
    def test_entitlement_subsystem_is_removed(self):
        licensing_dir = ROOT / "backend" / "app" / "licensing"
        self.assertFalse(any(licensing_dir.glob("*.py")))
        self.assertFalse((ROOT / "frontend" / "src" / "license.jsx").exists())
        self.assertFalse(
            (ROOT / "frontend" / "src" / "components" / "UpgradeGate.jsx").exists()
        )

    def test_private_service_and_gate_markers_are_absent(self):
        checked_suffixes = {".py", ".js", ".jsx", ".md", ".json", ".example"}
        ignored = {
            ROOT / "CHANGELOG.md",
            ROOT / "CODEX_SESSION.md",
            ROOT / "docs" / "OPEN_SOURCE_RELEASE_CHECKLIST.md",
            Path(__file__).resolve(),
        }
        banned = (
            "license.adventcybersecurity.com",
            "feature_gated",
            "BREACHWRIGHT_LICENSE",
            "Professional license",
            "Community Edition",
            "UpgradeGate",
        )

        failures = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path in ignored or path.suffix not in checked_suffixes:
                continue
            if ".git" in path.parts or "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in banned:
                if marker in text:
                    failures.append(f"{path.relative_to(ROOT)} contains {marker!r}")

        self.assertEqual([], failures)

    def test_attribution_and_license_files_exist(self):
        for name in ("LICENSE", "NOTICE", "TRADEMARKS.md", "SECURITY.md"):
            self.assertTrue((ROOT / name).is_file(), name)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Created by [Advent Cybersecurity]", readme)
        self.assertIn("Apache License 2.0", readme)

    def test_sensitive_downloads_require_bearer_authentication(self):
        reports_router = (
            ROOT / "backend" / "app" / "reports" / "router.py"
        ).read_text(encoding="utf-8")
        evidence_router = (
            ROOT / "backend" / "app" / "findings" / "evidence.py"
        ).read_text(encoding="utf-8")
        frontend_api = (ROOT / "frontend" / "src" / "api.js").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("download?token=", frontend_api)
        self.assertNotIn("token: str = None", reports_router)
        self.assertIn(
            "current_user: User = Depends(get_current_user)",
            reports_router,
        )
        self.assertIn(
            "current_user: User = Depends(get_current_user)",
            evidence_router,
        )
        self.assertNotIn(
            '@app.get("/api/evidence/{attachment_id}/file")',
            (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
