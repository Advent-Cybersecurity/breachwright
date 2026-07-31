"""End-to-end API test against a real Breachwright server and SQLite database."""

import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import shutil
import time
import unittest
import uuid
from contextlib import closing
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import httpx


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class UserJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_root = ROOT / f".breachwright-e2e-{uuid.uuid4().hex}"
        cls.temp_root.mkdir()
        cls.data_dir = cls.temp_root / "data"
        cls.database_path = cls.temp_root / "breachwright.db"
        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.log_path = cls.temp_root / "server.log"
        cls.log_file = cls.log_path.open("w+", encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "APPDATA": str(cls.temp_root / "appdata"),
                "XDG_DATA_HOME": str(cls.temp_root / "xdg"),
                "DATA_DIR": str(cls.data_dir),
                "DATABASE_URL": (
                    "sqlite+aiosqlite:///"
                    + cls.database_path.as_posix()
                ),
                "SECRET_KEY": "e2e-only-secret-key",
                "DESKTOP": "false",
                "PYTHONPATH": str(BACKEND),
                "PYTHONUNBUFFERED": "1",
            }
        )
        cls.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                str(BACKEND),
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
            ],
            cwd=ROOT,
            env=env,
            stdout=cls.log_file,
            stderr=subprocess.STDOUT,
        )

        deadline = time.monotonic() + 30
        last_error = None
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                break
            try:
                response = httpx.get(f"{cls.base_url}/api/health", timeout=1)
                if response.status_code == 200:
                    cls.client = httpx.Client(base_url=cls.base_url, timeout=20)
                    return
            except httpx.HTTPError as exc:
                last_error = exc
            time.sleep(0.1)

        cls.log_file.flush()
        logs = cls.log_path.read_text(encoding="utf-8", errors="replace")
        cls._stop_server()
        raise RuntimeError(
            f"Breachwright server did not become healthy: {last_error}\n{logs}"
        )

    @classmethod
    def _stop_server(cls):
        process = getattr(cls, "process", None)
        if process and process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    [
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            else:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    @classmethod
    def tearDownClass(cls):
        client = getattr(cls, "client", None)
        if client:
            client.close()
        cls._stop_server()
        log_file = getattr(cls, "log_file", None)
        if log_file:
            log_file.close()
        temp_root = getattr(cls, "temp_root", None)
        if temp_root:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_complete_first_run_to_report_and_export(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["distribution"], "open_source")
        self.assertEqual(health.headers["x-frame-options"], "DENY")
        self.assertEqual(
            health.headers["x-content-type-options"],
            "nosniff",
        )
        self.assertEqual(health.headers["cache-control"], "no-store")
        self.assertIn(
            "frame-ancestors 'none'",
            health.headers["content-security-policy"],
        )
        traversal = self.client.get("/..%2FREADME.md")
        if (ROOT / "frontend" / "dist" / "index.html").is_file():
            self.assertEqual(traversal.status_code, 200)
            self.assertIn('<div id="root">', traversal.text)
        else:
            self.assertEqual(traversal.status_code, 404)
        self.assertNotIn("# Breachwright", traversal.text)

        unauthorized = self.client.get("/api/engagements")
        self.assertEqual(unauthorized.status_code, 401)

        setup_state = self.client.get("/api/auth/needs-setup")
        self.assertEqual(setup_state.json(), {"needs_setup": True})

        weak_setup = self.client.post(
            "/api/auth/setup",
            json={
                "email": "admin@example.com",
                "password": "too-short",
            },
        )
        self.assertEqual(weak_setup.status_code, 422)

        invalid_email = self.client.post(
            "/api/auth/setup",
            json={
                "email": "not-an-email",
                "password": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(invalid_email.status_code, 422)
        blank_display_name = self.client.post(
            "/api/auth/setup",
            json={
                "email": "admin@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "   ",
            },
        )
        self.assertEqual(blank_display_name.status_code, 422)
        oversized_bcrypt_password = self.client.post(
            "/api/auth/setup",
            json={
                "email": "admin@example.com",
                "password": "\u00e9" * 40,
            },
        )
        self.assertEqual(oversized_bcrypt_password.status_code, 422)

        setup = self.client.post(
            "/api/auth/setup",
            json={
                "email": "admin@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "E2E Admin",
            },
        )
        self.assertEqual(setup.status_code, 200, setup.text)

        repeated_setup = self.client.post(
            "/api/auth/setup",
            json={
                "email": "other@example.com",
                "password": "unused-password",
            },
        )
        self.assertEqual(repeated_setup.status_code, 403)

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertIn("Path=/;", login.headers["set-cookie"])
        refreshed = self.client.post("/api/auth/refresh")
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "admin")

        analyst = self.client.post(
            "/api/auth/users",
            headers=headers,
            json={
                "email": "analyst@example.com",
                "password": "analyst-test-password",
                "display_name": "E2E Analyst",
                "role": "analyst",
            },
        )
        self.assertEqual(analyst.status_code, 200, analyst.text)
        duplicate_analyst = self.client.post(
            "/api/auth/users",
            headers=headers,
            json={
                "email": "ANALYST@example.com",
                "password": "another-test-password",
                "role": "analyst",
            },
        )
        self.assertEqual(duplicate_analyst.status_code, 409)

        viewer = self.client.post(
            "/api/auth/users",
            headers=headers,
            json={
                "email": "viewer@example.com",
                "password": "viewer-test-password",
                "display_name": "E2E Viewer",
                "role": "viewer",
            },
        )
        self.assertEqual(viewer.status_code, 200, viewer.text)
        users = self.client.get("/api/auth/users", headers=headers)
        self.assertEqual(users.status_code, 200, users.text)
        self.assertEqual(len(users.json()), 3)
        fallback_name_user = self.client.post(
            "/api/auth/users",
            headers=headers,
            json={
                "email": "fallback-name@example.com",
                "password": "fallback-test-password",
                "role": "viewer",
            },
        )
        self.assertEqual(
            fallback_name_user.status_code,
            200,
            fallback_name_user.text,
        )
        self.assertEqual(fallback_name_user.json()["display_name"], "fallback-name")
        updated_viewer = self.client.patch(
            f"/api/auth/users/{viewer.json()['id']}",
            headers=headers,
            json={"display_name": "Updated E2E Viewer"},
        )
        self.assertEqual(updated_viewer.status_code, 200, updated_viewer.text)
        self.assertEqual(updated_viewer.json()["display_name"], "Updated E2E Viewer")
        self_update = self.client.patch(
            f"/api/auth/users/{me.json()['id']}",
            headers=headers,
            json={"role": "analyst"},
        )
        self.assertEqual(self_update.status_code, 400, self_update.text)
        old_refresh_cookie = next(
            cookie
            for cookie in self.client.cookies.jar
            if cookie.name == "refresh_token" and cookie.path == "/"
        )

        wrong_password_change = self.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "current_password": "not-the-current-password",
                "new_password": "replacement-admin-password",
            },
        )
        self.assertEqual(
            wrong_password_change.status_code,
            400,
            wrong_password_change.text,
        )
        reused_password = self.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "current_password": "correct-horse-battery-staple",
                "new_password": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(reused_password.status_code, 400, reused_password.text)
        changed_password = self.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "current_password": "correct-horse-battery-staple",
                "new_password": "replacement-admin-password",
            },
        )
        self.assertEqual(changed_password.status_code, 200, changed_password.text)
        revoked_access = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(revoked_access.status_code, 401, revoked_access.text)
        self.client.cookies.set(
            old_refresh_cookie.name,
            old_refresh_cookie.value,
            domain=old_refresh_cookie.domain,
            path=old_refresh_cookie.path,
        )
        revoked_refresh = self.client.post("/api/auth/refresh")
        self.assertEqual(revoked_refresh.status_code, 401, revoked_refresh.text)
        old_password_login = self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
        self.assertEqual(old_password_login.status_code, 401, old_password_login.text)
        replacement_login = self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "replacement-admin-password",
            },
        )
        self.assertEqual(replacement_login.status_code, 200, replacement_login.text)
        replacement_refresh = self.client.post("/api/auth/refresh")
        self.assertEqual(
            replacement_refresh.status_code,
            200,
            replacement_refresh.text,
        )
        token = replacement_refresh.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        viewer_login = self.client.post(
            "/api/auth/login",
            json={
                "email": "viewer@example.com",
                "password": "viewer-test-password",
            },
        )
        self.assertEqual(viewer_login.status_code, 200, viewer_login.text)
        viewer_headers = {
            "Authorization": f"Bearer {viewer_login.json()['access_token']}"
        }
        viewer_users = self.client.get("/api/auth/users", headers=viewer_headers)
        self.assertEqual(viewer_users.status_code, 403, viewer_users.text)
        viewer_list = self.client.get(
            "/api/engagements",
            headers=viewer_headers,
        )
        self.assertEqual(viewer_list.status_code, 200, viewer_list.text)
        viewer_create = self.client.post(
            "/api/engagements",
            headers=viewer_headers,
            json={
                "name": "Viewer Must Not Create",
                "client_name": "Example Client",
            },
        )
        self.assertEqual(viewer_create.status_code, 403, viewer_create.text)
        viewer_template = self.client.post(
            "/api/report-templates",
            headers=viewer_headers,
            data={"name": "Viewer Must Not Create"},
        )
        self.assertEqual(viewer_template.status_code, 403, viewer_template.text)

        invalid_provider = self.client.put(
            "/api/settings/provider",
            headers=headers,
            json={"ai_provider": "advent-hosted"},
        )
        self.assertEqual(invalid_provider.status_code, 422)
        injected_provider = self.client.put(
            "/api/settings/provider",
            headers=headers,
            json={"anthropic_model": "model\nOPENAI_API_KEY=injected"},
        )
        self.assertEqual(injected_provider.status_code, 422)

        diagnostics = self.client.get("/api/system/diagnostics", headers=headers)
        self.assertEqual(diagnostics.status_code, 200, diagnostics.text)
        self.assertEqual(diagnostics.json()["database_type"], "sqlite")
        self.assertEqual(diagnostics.json()["database_integrity"], "ok")
        self.assertTrue(diagnostics.json()["data_directory_writable"])

        unsafe_logo = self.client.post(
            "/api/report-templates",
            headers=headers,
            data={"name": "Unsafe SVG"},
            files={
                "logo": (
                    "logo.svg",
                    b"<svg><script>alert(1)</script></svg>",
                    "image/svg+xml",
                )
            },
        )
        self.assertEqual(unsafe_logo.status_code, 400)

        spoofed_logo = self.client.post(
            "/api/report-templates",
            headers=headers,
            data={"name": "Spoofed PNG"},
            files={
                "logo": (
                    "logo.png",
                    b"<html>not an image</html>",
                    "image/png",
                )
            },
        )
        self.assertEqual(spoofed_logo.status_code, 400)

        invalid_engagement = self.client.post(
            "/api/engagements",
            headers=headers,
            json={
                "name": "Invalid Dates",
                "client_name": "Example Client",
                "start_date": "2026-07-15",
                "end_date": "2026-07-01",
            },
        )
        self.assertEqual(invalid_engagement.status_code, 422)
        missing_checklist = self.client.post(
            "/api/engagements/missing/checklists/ptes",
            headers=headers,
        )
        self.assertEqual(missing_checklist.status_code, 404)
        missing_job = self.client.post(
            "/api/jobs",
            headers=headers,
            json={
                "engagement_id": "missing",
                "tool": "custom",
                "command": "echo should-not-run",
            },
        )
        self.assertEqual(missing_job.status_code, 404)

        engagement = self.client.post(
            "/api/engagements",
            headers=headers,
            json={
                "name": "Release Candidate Assessment",
                "client_name": "Example Client",
                "scope": "example.test and 10.0.0.0/24",
                "start_date": "2026-07-01",
                "end_date": "2026-07-15",
            },
        )
        self.assertEqual(engagement.status_code, 201, engagement.text)
        engagement_id = engagement.json()["id"]

        viewer_detail = self.client.get(
            f"/api/engagements/{engagement_id}",
            headers=viewer_headers,
        )
        self.assertEqual(viewer_detail.status_code, 200, viewer_detail.text)
        viewer_update = self.client.put(
            f"/api/engagements/{engagement_id}",
            headers=viewer_headers,
            json={"name": "Viewer Must Not Update"},
        )
        self.assertEqual(viewer_update.status_code, 403, viewer_update.text)
        viewer_finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            headers=viewer_headers,
            json={"title": "Viewer Must Not Create", "severity": "low"},
        )
        self.assertEqual(viewer_finding.status_code, 403, viewer_finding.text)
        viewer_report = self.client.post(
            f"/api/engagements/{engagement_id}/reports",
            headers=viewer_headers,
        )
        self.assertEqual(viewer_report.status_code, 403, viewer_report.text)
        viewer_narrative = self.client.post(
            f"/api/engagements/{engagement_id}/narrative/full/save",
            headers=viewer_headers,
            json={"narrative": "viewer must not save"},
        )
        self.assertEqual(
            viewer_narrative.status_code,
            403,
            viewer_narrative.text,
        )
        viewer_job = self.client.post(
            "/api/jobs",
            headers=viewer_headers,
            json={
                "engagement_id": engagement_id,
                "tool": "custom",
                "command": "echo should-not-run",
            },
        )
        self.assertEqual(viewer_job.status_code, 403, viewer_job.text)
        deactivated_viewer = self.client.patch(
            f"/api/auth/users/{viewer.json()['id']}",
            headers=headers,
            json={"is_active": False},
        )
        self.assertEqual(deactivated_viewer.status_code, 200, deactivated_viewer.text)
        self.assertFalse(deactivated_viewer.json()["is_active"])
        inactive_viewer = self.client.get(
            "/api/engagements",
            headers=viewer_headers,
        )
        self.assertEqual(inactive_viewer.status_code, 401, inactive_viewer.text)
        reactivated_viewer = self.client.patch(
            f"/api/auth/users/{viewer.json()['id']}",
            headers=headers,
            json={"is_active": True},
        )
        self.assertEqual(reactivated_viewer.status_code, 200, reactivated_viewer.text)
        self.assertTrue(reactivated_viewer.json()["is_active"])

        job = self.client.post(
            "/api/jobs",
            headers=headers,
            json={
                "engagement_id": engagement_id,
                "tool": "custom",
                "command": "echo breachwright-job-ok",
            },
        )
        self.assertEqual(job.status_code, 201, job.text)
        job_id = job.json()["id"]
        job_state = None
        for _ in range(50):
            job_response = self.client.get(
                f"/api/jobs/{job_id}",
                headers=headers,
            )
            self.assertEqual(job_response.status_code, 200, job_response.text)
            job_state = job_response.json()
            if job_state["status"] in {"complete", "failed"}:
                break
            time.sleep(0.1)
        self.assertEqual(job_state["status"], "complete", job_state)
        self.assertIn("breachwright-job-ok", job_state["output"])
        saved_narrative = self.client.post(
            f"/api/engagements/{engagement_id}/narrative/full/save",
            headers=headers,
            json={"narrative": "Validated local narrative"},
        )
        self.assertEqual(saved_narrative.status_code, 200, saved_narrative.text)

        scan_upload = self.client.post(
            f"/api/engagements/{engagement_id}/upload-scan",
            headers=headers,
            params={"scan_type": "custom"},
            files={
                "file": (
                    "../../outside.txt",
                    b"safe scan content",
                    "text/plain",
                )
            },
        )
        self.assertEqual(scan_upload.status_code, 200, scan_upload.text)
        self.assertEqual(scan_upload.json()["filename"], "outside.txt")
        upload_directory = self.data_dir / "uploads" / engagement_id
        uploaded_files = list(upload_directory.iterdir())
        self.assertEqual(len(uploaded_files), 1)
        self.assertEqual(uploaded_files[0].parent, upload_directory)
        self.assertFalse((self.data_dir / "outside.txt").exists())

        invalid_finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            headers=headers,
            json={
                "title": "Invalid score",
                "severity": "high",
                "cvss_score": 10.1,
            },
        )
        self.assertEqual(invalid_finding.status_code, 422)

        finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            headers=headers,
            json={
                "title": "Outdated service",
                "description": "A network service is outdated.",
                "severity": "high",
                "cvss_score": 8.1,
                "affected_hosts": "10.0.0.5",
                "evidence": "Version response captured during testing.",
                "remediation": "Install the currently supported release.",
            },
        )
        self.assertEqual(finding.status_code, 201, finding.text)
        finding_id = finding.json()["id"]
        invalid_retest = self.client.put(
            f"/api/engagements/{engagement_id}/findings/{finding_id}",
            headers=headers,
            json={"retest_status": "unrecognized-state"},
        )
        self.assertEqual(invalid_retest.status_code, 422, invalid_retest.text)

        checklist = self.client.post(
            f"/api/engagements/{engagement_id}/checklists/ptes",
            headers=headers,
        )
        self.assertEqual(checklist.status_code, 200, checklist.text)
        self.assertGreater(checklist.json()["items_created"], 0)

        sharphound_buffer = BytesIO()
        with ZipFile(
            sharphound_buffer,
            "w",
            compression=ZIP_DEFLATED,
        ) as archive:
            archive.writestr(
                "users.json",
                json.dumps(
                    {
                        "data": [
                            {
                                "ObjectIdentifier": "S-1-5-21-1000",
                                "Properties": {
                                    "name": "USER@EXAMPLE.COM",
                                    "domain": "EXAMPLE.COM",
                                    "enabled": True,
                                },
                            }
                        ]
                    }
                ),
            )
        ad_import = self.client.post(
            f"/api/engagements/{engagement_id}/ad/import",
            headers=headers,
            files={
                "file": (
                    "sharphound.zip",
                    sharphound_buffer.getvalue(),
                    "application/zip",
                )
            },
        )
        self.assertEqual(ad_import.status_code, 200, ad_import.text)
        self.assertEqual(ad_import.json()["object_count"], 1)

        disguised_evidence = self.client.post(
            f"/api/engagements/{engagement_id}/findings/{finding_id}/evidence",
            headers=headers,
            files={
                "file": (
                    "disguised.png",
                    b"<html><script>alert('not an image')</script></html>",
                    "image/png",
                )
            },
        )
        self.assertEqual(
            disguised_evidence.status_code,
            415,
            disguised_evidence.text,
        )

        evidence_bytes = b"\x89PNG\r\n\x1a\nbreachwright-e2e"
        upload = self.client.post(
            f"/api/engagements/{engagement_id}/findings/{finding_id}/evidence",
            headers=headers,
            files={"file": ("../evidence.png", evidence_bytes, "image/png")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json()["filename"], "evidence.png")
        evidence_url = upload.json()["url"]

        self.assertEqual(self.client.get(evidence_url).status_code, 401)
        downloaded_evidence = self.client.get(evidence_url, headers=headers)
        self.assertEqual(downloaded_evidence.status_code, 200)
        self.assertEqual(downloaded_evidence.content, evidence_bytes)
        self.assertEqual(
            downloaded_evidence.headers["x-content-type-options"],
            "nosniff",
        )

        bulk_cleanup_finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            headers=headers,
            json={
                "title": "Bulk cleanup finding",
                "severity": "low",
            },
        )
        self.assertEqual(
            bulk_cleanup_finding.status_code,
            201,
            bulk_cleanup_finding.text,
        )
        bulk_cleanup_id = bulk_cleanup_finding.json()["id"]
        bulk_cleanup_upload = self.client.post(
            (
                f"/api/engagements/{engagement_id}/findings/"
                f"{bulk_cleanup_id}/evidence"
            ),
            headers=headers,
            files={
                "file": (
                    "bulk-cleanup.png",
                    evidence_bytes,
                    "image/png",
                )
            },
        )
        self.assertEqual(
            bulk_cleanup_upload.status_code,
            200,
            bulk_cleanup_upload.text,
        )
        bulk_evidence_directory = self.data_dir / "evidence" / bulk_cleanup_id
        self.assertTrue(bulk_evidence_directory.is_dir())
        bulk_delete = self.client.post(
            f"/api/engagements/{engagement_id}/findings/bulk",
            headers=headers,
            json={
                "finding_ids": [bulk_cleanup_id],
                "action": "delete",
            },
        )
        self.assertEqual(bulk_delete.status_code, 200, bulk_delete.text)
        self.assertEqual(bulk_delete.json()["count"], 1)
        self.assertFalse(bulk_evidence_directory.exists())

        markdown_report = self.client.post(
            f"/api/engagements/{engagement_id}/reports",
            headers=headers,
            params={"format": "md"},
        )
        self.assertEqual(markdown_report.status_code, 201, markdown_report.text)
        report_id = markdown_report.json()["id"]
        report_download = self.client.get(
            f"/api/reports/{report_id}/download",
            headers=headers,
        )
        self.assertEqual(report_download.status_code, 200)
        report_text = report_download.text
        self.assertIn("Release Candidate Assessment", report_text)
        self.assertIn("created by Advent Cybersecurity", report_text)
        self.assertIn("Outdated service", report_text)

        docx_report = self.client.post(
            f"/api/engagements/{engagement_id}/reports",
            headers=headers,
            params={"format": "docx"},
        )
        self.assertEqual(docx_report.status_code, 201, docx_report.text)
        docx_download = self.client.get(
            f"/api/reports/{docx_report.json()['id']}/download",
            headers=headers,
        )
        self.assertEqual(docx_download.status_code, 200)
        self.assertTrue(docx_download.content.startswith(b"PK"))

        export = self.client.get(
            f"/api/engagements/{engagement_id}/export",
            headers=headers,
        )
        self.assertEqual(export.status_code, 200)
        exported = export.json()
        self.assertEqual(exported["engagement"]["name"], "Release Candidate Assessment")
        self.assertEqual(exported["findings"][0]["title"], "Outdated service")

        invalid_export = json.loads(json.dumps(exported))
        invalid_export["findings"][0]["severity"] = "extreme"
        rejected_import = self.client.post(
            "/api/engagements/import",
            headers=headers,
            files={
                "file": (
                    "invalid-engagement.json",
                    json.dumps(invalid_export).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(rejected_import.status_code, 422, rejected_import.text)
        after_rejected_import = self.client.get(
            "/api/engagements",
            headers=headers,
        )
        self.assertEqual(len(after_rejected_import.json()), 1)

        imported = self.client.post(
            "/api/engagements/import",
            headers=headers,
            files={
                "file": (
                    "engagement.json",
                    json.dumps(exported).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["findings_imported"], 1)

        engagements = self.client.get("/api/engagements", headers=headers)
        self.assertEqual(engagements.status_code, 200)
        self.assertEqual(len(engagements.json()), 2)
        self.assertEqual(
            sorted(item["finding_count"] for item in engagements.json()),
            [1, 1],
        )

        backup = self.client.post("/api/system/backups", headers=headers)
        self.assertEqual(backup.status_code, 201, backup.text)
        backup_name = backup.json()["filename"]
        backup_download = self.client.get(
            f"/api/system/backups/{backup_name}",
            headers=headers,
        )
        self.assertEqual(backup_download.status_code, 200)
        self.assertTrue(backup_download.content.startswith(b"PK"))
        self.assertEqual(
            backup_download.headers["x-content-type-options"],
            "nosniff",
        )
        deleted_backup = self.client.delete(
            f"/api/system/backups/{backup_name}",
            headers=headers,
        )
        self.assertEqual(deleted_backup.status_code, 204, deleted_backup.text)
        self.assertEqual(
            self.client.get(
                f"/api/system/backups/{backup_name}",
                headers=headers,
            ).status_code,
            404,
        )

        evidence_directory = self.data_dir / "evidence" / finding_id
        reports_directory = self.data_dir / "reports" / engagement_id
        self.assertTrue(evidence_directory.is_dir())
        self.assertTrue(reports_directory.is_dir())
        deleted = self.client.delete(
            f"/api/engagements/{engagement_id}",
            headers=headers,
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertFalse(evidence_directory.exists())
        self.assertFalse(reports_directory.exists())
        self.assertEqual(
            self.client.get(evidence_url, headers=headers).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/reports/{report_id}/download",
                headers=headers,
            ).status_code,
            404,
        )
        with closing(sqlite3.connect(self.database_path)) as connection:
            checklist_count = connection.execute(
                "SELECT COUNT(*) FROM methodology_checklists "
                "WHERE engagement_id = ?",
                (engagement_id,),
            ).fetchone()[0]
            ad_object_count = connection.execute(
                "SELECT COUNT(*) FROM ad_objects"
            ).fetchone()[0]
            ad_relationship_count = connection.execute(
                "SELECT COUNT(*) FROM ad_relationships"
            ).fetchone()[0]
            job_count = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE engagement_id = ?",
                (engagement_id,),
            ).fetchone()[0]
            narrative_count = connection.execute(
                "SELECT COUNT(*) FROM app_settings WHERE key = ?",
                (f"narrative_{engagement_id}",),
            ).fetchone()[0]
        self.assertEqual(checklist_count, 0)
        self.assertEqual(ad_object_count, 0)
        self.assertEqual(ad_relationship_count, 0)
        self.assertEqual(job_count, 0)
        self.assertEqual(narrative_count, 0)
        self.assertFalse((self.data_dir / "jobs" / job_id).exists())


if __name__ == "__main__":
    unittest.main()
