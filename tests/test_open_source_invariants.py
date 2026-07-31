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

    def test_local_workspace_has_no_account_or_token_surface(self):
        reports_router = (
            ROOT / "backend" / "app" / "reports" / "router.py"
        ).read_text(encoding="utf-8")
        evidence_router = (
            ROOT / "backend" / "app" / "findings" / "evidence.py"
        ).read_text(encoding="utf-8")
        frontend_api = (ROOT / "frontend" / "src" / "api.js").read_text(
            encoding="utf-8"
        )
        frontend_app = (ROOT / "frontend" / "src" / "App.jsx").read_text(
            encoding="utf-8"
        )
        frontend_layout = (
            ROOT / "frontend" / "src" / "components" / "Layout.jsx"
        ).read_text(encoding="utf-8")
        frontend_settings = (
            ROOT / "frontend" / "src" / "pages" / "Settings.jsx"
        ).read_text(encoding="utf-8")
        installers = (
            (ROOT / "install-windows.bat").read_text(encoding="utf-8"),
            (ROOT / "install.sh").read_text(encoding="utf-8"),
        )

        main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        requirements = (ROOT / "backend" / "requirements.txt").read_text(
            encoding="utf-8"
        )

        for path in (
            ROOT / "backend" / "app" / "auth" / "router.py",
            ROOT / "backend" / "app" / "auth" / "service.py",
            ROOT / "frontend" / "src" / "pages" / "Login.jsx",
            ROOT / "frontend" / "src" / "pages" / "Setup.jsx",
        ):
            self.assertFalse(path.exists(), path)

        self.assertNotIn("auth_router", main)
        self.assertNotIn("Authorization", frontend_api)
        self.assertNotIn("accessToken", frontend_api)
        self.assertNotIn("import('./pages/Login')", frontend_app)
        self.assertNotIn("import('./pages/Setup')", frontend_app)
        self.assertNotIn("Logout", frontend_layout)
        self.assertNotIn("User Management", frontend_settings)
        self.assertNotIn("Change Password", frontend_settings)
        for installer in installers:
            self.assertNotIn("--setup", installer)
            self.assertNotIn("Create your admin account", installer)
        self.assertNotIn("PyJWT", requirements)
        self.assertNotIn("passlib", requirements)
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
            main,
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

    def test_frontend_assets_use_server_root_for_deep_links(self):
        vite_config = (ROOT / "frontend" / "vite.config.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("base: '/'", vite_config)
        self.assertNotIn("base: './'", vite_config)

    def test_docker_application_data_is_persistent(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("- DATA_DIR=/app/data", compose)
        self.assertIn("- ./data:/app/data", compose)
        self.assertNotIn("./data/uploads:/app/data/uploads", compose)
        self.assertNotIn("./data/reports:/app/data/reports", compose)
        self.assertIn('- "127.0.0.1:80:80"', compose)
        self.assertNotIn('- "13370:13370"', compose)

        launcher = (ROOT / "run.py").read_text(encoding="utf-8")
        self.assertIn('choices=("127.0.0.1", "localhost")', launcher)

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

    def test_zero_cvss_is_not_treated_as_missing(self):
        for path in (ROOT / "backend" / "app").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("cvss_score or 'N/A'", source, path)
            self.assertNotIn('cvss_score or "N/A"', source, path)

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

    def test_release_automation_has_zero_cost_compute_guardrails(self):
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in (ROOT / ".github" / "workflows").glob("*.yml")
        }
        self.assertEqual(
            {"candidate-build.yml", "ci.yml", "codeql.yml"},
            set(workflows),
        )
        for name, source in workflows.items():
            self.assertIn("cancel-in-progress: true", source, name)
            self.assertNotIn("self-hosted", source, name)
            self.assertNotIn("actions/upload-artifact", source, name)

        candidate = workflows["candidate-build.yml"]
        self.assertIn("timeout-minutes: 30", candidate)
        self.assertIn("timeout-minutes: 10", candidate)
        self.assertIn("Acquire::Retries=3", candidate)
        self.assertIn("ubuntu-latest", candidate)
        self.assertIn("windows-latest", candidate)


if __name__ == "__main__":
    unittest.main()
