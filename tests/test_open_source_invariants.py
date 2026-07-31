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

    def test_docx_generation_runs_off_event_loop(self):
        reports_router = (
            ROOT / "backend" / "app" / "reports" / "router.py"
        ).read_text(encoding="utf-8")

        self.assertIn("await asyncio.to_thread(", reports_router)
        self.assertIn("generate_docx_report,", reports_router)

    def test_chat_content_is_not_rendered_as_raw_html(self):
        assistant = (
            ROOT / "frontend" / "src" / "pages" / "Assistant.jsx"
        ).read_text(encoding="utf-8")
        self.assertNotIn("dangerouslySetInnerHTML", assistant)

    def test_docker_application_data_is_persistent(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("- DATA_DIR=/app/data", compose)
        self.assertIn("- ./data:/app/data", compose)
        self.assertNotIn("./data/uploads:/app/data/uploads", compose)
        self.assertNotIn("./data/reports:/app/data/reports", compose)

    def test_upload_routes_do_not_read_unbounded_requests(self):
        upload_routes = (
            ROOT / "backend" / "app" / "analysis" / "router.py",
            ROOT / "backend" / "app" / "findings" / "evidence.py",
            ROOT / "backend" / "app" / "reports" / "template_router.py",
            ROOT / "backend" / "app" / "ad" / "router.py",
            ROOT / "backend" / "app" / "engagements" / "export_import.py",
        )
        for path in upload_routes:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("await file.read()", source, path)
            self.assertNotIn("await logo.read()", source, path)

    def test_advertised_bedrock_provider_is_installed_and_packaged(self):
        requirements = (ROOT / "backend" / "requirements.txt").read_text(
            encoding="utf-8"
        )
        specification = (ROOT / "breachwright.spec").read_text(encoding="utf-8")
        self.assertIn("boto3==", requirements)
        self.assertIn('"boto3", "botocore"', specification)
        excludes = specification.split("_excludes = [", 1)[1].split("]", 1)[0]
        self.assertNotIn('"boto3"', excludes)
        self.assertNotIn('"botocore"', excludes)


if __name__ == "__main__":
    unittest.main()
