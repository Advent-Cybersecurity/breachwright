"""End-to-end API test against a real Breachwright server and SQLite database."""

import json
import csv
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
from io import BytesIO, StringIO
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
        cls._cleanup_test_workspace()
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
    def _cleanup_test_workspace(cls):
        log_file = getattr(cls, "log_file", None)
        if log_file and not log_file.closed:
            log_file.close()
        temp_root = getattr(cls, "temp_root", None)
        if temp_root:
            shutil.rmtree(temp_root, ignore_errors=True)

    @classmethod
    def tearDownClass(cls):
        client = getattr(cls, "client", None)
        if client:
            client.close()
        cls._stop_server()
        cls._cleanup_test_workspace()

    def test_complete_local_workspace_to_report_and_export(self):
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
        missing_api_route = self.client.get("/api/does-not-exist")
        self.assertEqual(missing_api_route.status_code, 404)
        traversal = self.client.get("/..%2FREADME.md")
        if (ROOT / "frontend" / "dist" / "index.html").is_file():
            self.assertEqual(traversal.status_code, 200)
            self.assertIn('<div id="root">', traversal.text)
        else:
            self.assertEqual(traversal.status_code, 404)
        self.assertNotIn("# Breachwright", traversal.text)

        workspace = self.client.get("/api/engagements")
        self.assertEqual(workspace.status_code, 200, workspace.text)
        self.assertEqual(workspace.json(), [])
        headers = {}
        for retired_route in (
            "/api/auth/needs-setup",
            "/api/auth/login",
            "/api/auth/refresh",
            "/api/auth/me",
            "/api/auth/users",
        ):
            retired = self.client.get(retired_route)
            self.assertEqual(retired.status_code, 404, retired.text)

        with closing(sqlite3.connect(self.database_path)) as connection:
            owner = connection.execute(
                "SELECT email, display_name, role, is_active FROM users"
            ).fetchall()
        self.assertEqual(
            owner,
            [("local@breachwright.invalid", "Local Owner", "admin", 1)],
        )
        empty_assistant_message = self.client.post(
            "/api/assistant/chat",
            headers=headers,
            json={"message": ""},
        )
        self.assertEqual(empty_assistant_message.status_code, 422)
        oversized_assistant_message = self.client.post(
            "/api/assistant/chat",
            headers=headers,
            json={"message": "x" * 20001},
        )
        self.assertEqual(oversized_assistant_message.status_code, 422)
        missing_assistant_context = self.client.post(
            "/api/assistant/chat",
            headers=headers,
            json={
                "message": "Summarize this engagement",
                "engagement_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        self.assertEqual(
            missing_assistant_context.status_code,
            404,
            missing_assistant_context.text,
        )

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
        invalid_azure_endpoint = self.client.put(
            "/api/settings/provider",
            headers=headers,
            json={"azure_openai_endpoint": "file:///not-a-model-endpoint"},
        )
        self.assertEqual(invalid_azure_endpoint.status_code, 422)
        provider_settings = self.client.get("/api/settings/provider", headers=headers)
        self.assertEqual(provider_settings.status_code, 200, provider_settings.text)
        self.assertTrue(provider_settings.json()["ai_redact_sensitive_data"])
        self.assertIn("bedrock_model_id", provider_settings.json())
        self.assertIn("azure_openai_api_version", provider_settings.json())

        diagnostics = self.client.get("/api/system/diagnostics", headers=headers)
        self.assertEqual(diagnostics.status_code, 200, diagnostics.text)
        self.assertEqual(diagnostics.json()["database_type"], "sqlite")
        self.assertEqual(diagnostics.json()["database_integrity"], "ok")
        self.assertTrue(diagnostics.json()["data_directory_writable"])
        self.assertEqual(diagnostics.json()["stored_files"]["status"], "ok")
        self.assertEqual(diagnostics.json()["stored_files"]["missing"], 0)
        self.assertTrue(diagnostics.json()["stored_files"]["complete"])
        support = self.client.get("/api/system/support-snapshot", headers=headers)
        self.assertEqual(support.status_code, 200, support.text)
        self.assertIn(
            "attachment; filename=\"breachwright-support-",
            support.headers["content-disposition"],
        )
        self.assertEqual(support.json()["schema_version"], 1)
        self.assertNotIn("data_directory", support.json()["diagnostics"])
        self.assertTrue(
            all(value is False for value in support.json()["privacy"].values())
        )
        self.assertNotIn("model_url", support.json()["ai"])

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

        valid_template = self.client.post(
            "/api/report-templates",
            headers=headers,
            data={
                "name": "Release Candidate Template",
                "company_name": "Example Client",
                "primary_color": "#112233",
                "secondary_color": "#445566",
                "header_text": "Authorized security assessment",
                "footer_text": "Confidential",
                "is_default": "true",
            },
            files={
                "logo": (
                    "brand.png",
                    b"\x89PNG\r\n\x1a\nbreachwright-template",
                    "image/png",
                )
            },
        )
        self.assertEqual(valid_template.status_code, 201, valid_template.text)
        template_id = valid_template.json()["id"]
        templates = self.client.get("/api/report-templates", headers=headers)
        self.assertEqual(templates.status_code, 200, templates.text)
        self.assertIn(
            template_id,
            {item["id"] for item in templates.json()},
        )
        template_logo_url = f"/api/report-templates/{template_id}/logo"
        template_logo = self.client.get(template_logo_url, headers=headers)
        self.assertEqual(template_logo.status_code, 200, template_logo.text)
        self.assertEqual(template_logo.headers["content-type"], "image/png")
        updated_template = self.client.put(
            f"/api/report-templates/{template_id}",
            headers=headers,
            data={
                "name": "Updated Release Candidate Template",
                "company_name": "Example Client",
                "primary_color": "#223344",
                "secondary_color": "#556677",
                "header_text": "Updated assessment",
                "footer_text": "Confidential",
                "is_default": "true",
            },
            files={
                "logo": (
                    "brand.jpg",
                    b"\xff\xd8\xffbreachwright-template",
                    "image/jpeg",
                )
            },
        )
        self.assertEqual(updated_template.status_code, 200, updated_template.text)
        updated_logo = self.client.get(template_logo_url, headers=headers)
        self.assertEqual(updated_logo.status_code, 200, updated_logo.text)
        self.assertEqual(updated_logo.headers["content-type"], "image/jpeg")
        deleted_template = self.client.delete(
            f"/api/report-templates/{template_id}",
            headers=headers,
        )
        self.assertEqual(deleted_template.status_code, 204, deleted_template.text)
        self.assertEqual(
            self.client.get(template_logo_url, headers=headers).status_code,
            404,
        )
        self.assertFalse((self.data_dir / "templates" / template_id).exists())

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
        self.assertEqual(
            self.client.get("/api/engagements/missing/reports").status_code,
            404,
        )
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
        oversized_bulk_selection = self.client.post(
            f"/api/engagements/{engagement_id}/findings/bulk",
            headers=headers,
            json={
                "finding_ids": ["00000000-0000-0000-0000-000000000000"] * 1001,
                "action": "delete",
            },
        )
        self.assertEqual(oversized_bulk_selection.status_code, 422)

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
        saved_job_note = self.client.post(
            f"/api/jobs/{job_id}/notebook",
            json={"title": "Command validation output", "tags": ["custom", "validation"]},
        )
        self.assertEqual(saved_job_note.status_code, 201, saved_job_note.text)
        self.assertEqual(saved_job_note.json()["source_type"], "tool_runner_job")
        self.assertEqual(saved_job_note.json()["source_id"], job_id)
        self.assertIn("echo breachwright-job-ok", saved_job_note.json()["body"])
        self.assertIn("breachwright-job-ok", saved_job_note.json()["body"])
        job_with_note = self.client.get(f"/api/jobs/{job_id}", headers=headers)
        self.assertEqual(
            job_with_note.json()["notebook_note_id"],
            saved_job_note.json()["id"],
        )
        duplicate_job_note = self.client.post(
            f"/api/jobs/{job_id}/notebook",
            json={},
        )
        self.assertEqual(duplicate_job_note.status_code, 409, duplicate_job_note.text)
        scan_job = self.client.post(
            "/api/jobs",
            headers=headers,
            json={
                "engagement_id": engagement_id,
                "tool": "nmap",
                "command": "echo Nmap scan report for 192.0.2.10 > output.txt",
            },
        )
        self.assertEqual(scan_job.status_code, 201, scan_job.text)
        scan_job_id = scan_job.json()["id"]
        scan_job_state = None
        for _ in range(50):
            scan_job_response = self.client.get(
                f"/api/jobs/{scan_job_id}",
                headers=headers,
            )
            self.assertEqual(scan_job_response.status_code, 200, scan_job_response.text)
            scan_job_state = scan_job_response.json()
            if scan_job_state["status"] in {"complete", "failed"}:
                break
            time.sleep(0.1)
        self.assertEqual(scan_job_state["status"], "complete", scan_job_state)
        self.assertIn("Nmap scan report for 192.0.2.10", scan_job_state["output"])
        self.assertIsNotNone(scan_job_state["completed_at"])
        job_scan = self.client.post(f"/api/jobs/{scan_job_id}/scan", headers=headers)
        self.assertEqual(job_scan.status_code, 201, job_scan.text)
        self.assertEqual(job_scan.json()["scan_type"], "nmap")
        self.assertEqual(job_scan.json()["source_job_id"], scan_job_id)
        linked_scan_job = self.client.get(f"/api/jobs/{scan_job_id}", headers=headers)
        self.assertEqual(linked_scan_job.json()["scan_upload_id"], job_scan.json()["id"])
        duplicate_job_scan = self.client.post(f"/api/jobs/{scan_job_id}/scan", headers=headers)
        self.assertEqual(duplicate_job_scan.status_code, 409, duplicate_job_scan.text)
        limited_jobs = self.client.get(
            f"/api/jobs?engagement_id={engagement_id}&limit=1",
            headers=headers,
        )
        self.assertEqual(limited_jobs.status_code, 200, limited_jobs.text)
        self.assertEqual(len(limited_jobs.json()), 1)
        self.assertEqual(limited_jobs.json()[0]["id"], scan_job_id)
        self.assertEqual(
            self.client.get(
                f"/api/jobs?engagement_id={engagement_id}&limit=0",
                headers=headers,
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                f"/api/jobs?engagement_id={engagement_id}&limit=201",
                headers=headers,
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.delete(f"/api/jobs/{scan_job_id}", headers=headers).status_code,
            204,
        )
        scans_after_job_delete = self.client.get(
            f"/api/engagements/{engagement_id}/scans",
            headers=headers,
        )
        self.assertIn(
            job_scan.json()["id"],
            {item["id"] for item in scans_after_job_delete.json()},
        )
        self.assertEqual(
            self.client.delete(
                f"/api/engagements/{engagement_id}/scans/{job_scan.json()['id']}",
                headers=headers,
            ).status_code,
            204,
        )
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
                    "../../outside.txt:alternate",
                    b"safe scan content",
                    "text/plain",
                )
            },
        )
        self.assertEqual(scan_upload.status_code, 200, scan_upload.text)
        self.assertEqual(
            scan_upload.json()["filename"],
            "outside.txt:alternate",
        )
        upload_directory = self.data_dir / "uploads" / engagement_id
        uploaded_files = list(upload_directory.iterdir())
        self.assertEqual(len(uploaded_files), 1)
        self.assertEqual(uploaded_files[0].parent, upload_directory)
        self.assertEqual(uploaded_files[0].suffix, ".dat")
        self.assertNotIn(":", uploaded_files[0].name)
        self.assertFalse((self.data_dir / "outside.txt").exists())
        scans = self.client.get(
            f"/api/engagements/{engagement_id}/scans",
            headers=headers,
        )
        self.assertEqual(scans.status_code, 200, scans.text)
        self.assertEqual(len(scans.json()), 1)
        self.assertEqual(scans.json()[0]["id"], scan_upload.json()["id"])
        self.assertEqual(scans.json()[0]["size_bytes"], len(b"safe scan content"))
        self.assertTrue(scans.json()[0]["stored_file_available"])
        self.assertIsNotNone(scans.json()[0]["created_at"])
        correlated = self.client.post(
            f"/api/engagements/{engagement_id}/correlate",
            headers=headers,
        )
        self.assertEqual(correlated.status_code, 200, correlated.text)
        self.assertEqual(correlated.json()["stats"]["total_hosts"], 0)

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
        duplicate_check = self.client.post(
            f"/api/engagements/{engagement_id}/findings/duplicate-check",
            headers=headers,
            json={
                "title": "  OUTDATED SERVICE  ",
                "affected_hosts": "10.0.0.5, 192.0.2.55",
            },
        )
        self.assertEqual(duplicate_check.status_code, 200, duplicate_check.text)
        self.assertEqual(duplicate_check.json()["count"], 1)
        self.assertEqual(duplicate_check.json()["matches"][0]["id"], finding_id)
        self.assertTrue(duplicate_check.json()["matches"][0]["host_overlap"])
        distinct_check = self.client.post(
            f"/api/engagements/{engagement_id}/findings/duplicate-check",
            headers=headers,
            json={"title": "Distinct finding"},
        )
        self.assertEqual(distinct_check.json()["count"], 0)
        saved_narrative = self.client.post(
            f"/api/engagements/{engagement_id}/narrative/full/save",
            headers=headers,
            json={
                "narrative": "Validated local narrative",
                "citations": [f"FINDING:{finding_id}"],
            },
        )
        self.assertEqual(saved_narrative.status_code, 200, saved_narrative.text)
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
        checklist_items = self.client.get(
            f"/api/engagements/{engagement_id}/checklists",
            headers=headers,
        )
        self.assertEqual(checklist_items.status_code, 200, checklist_items.text)
        self.assertGreater(len(checklist_items.json()), 0)
        checklist_item_id = checklist_items.json()[0]["id"]
        invalid_checklist_status = self.client.put(
            (
                f"/api/engagements/{engagement_id}/checklists/"
                f"{checklist_item_id}"
            ),
            headers=headers,
            json={"status": "unknown"},
        )
        self.assertEqual(
            invalid_checklist_status.status_code,
            422,
            invalid_checklist_status.text,
        )
        oversized_checklist_notes = self.client.put(
            (
                f"/api/engagements/{engagement_id}/checklists/"
                f"{checklist_item_id}"
            ),
            headers=headers,
            json={"status": "done", "notes": "x" * 200001},
        )
        self.assertEqual(oversized_checklist_notes.status_code, 422)
        updated_checklist = self.client.put(
            (
                f"/api/engagements/{engagement_id}/checklists/"
                f"{checklist_item_id}"
            ),
            headers=headers,
            json={
                "status": "done",
                "notes": "Validated during release testing",
            },
        )
        self.assertEqual(updated_checklist.status_code, 200, updated_checklist.text)
        checklist_progress = self.client.get(
            f"/api/engagements/{engagement_id}/checklists/progress",
            headers=headers,
        )
        self.assertEqual(checklist_progress.status_code, 200, checklist_progress.text)
        self.assertEqual(checklist_progress.json()["ptes"]["done"], 1)

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
        ad_imports = self.client.get(
            f"/api/engagements/{engagement_id}/ad/imports",
            headers=headers,
        )
        self.assertEqual(ad_imports.status_code, 200, ad_imports.text)
        self.assertEqual(len(ad_imports.json()), 1)
        self.assertEqual(ad_imports.json()[0]["id"], ad_import.json()["id"])
        ad_summary = self.client.get(
            f"/api/engagements/{engagement_id}/ad/summary",
            headers=headers,
        )
        self.assertEqual(ad_summary.status_code, 200, ad_summary.text)
        self.assertTrue(ad_summary.json()["has_data"])
        self.assertEqual(sum(ad_summary.json()["object_counts"].values()), 1)
        ad_paths = self.client.get(
            f"/api/engagements/{engagement_id}/ad/paths",
            headers=headers,
        )
        self.assertEqual(ad_paths.status_code, 200, ad_paths.text)
        self.assertEqual(ad_paths.json(), [])

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
            files={
                "file": (
                    "../evidence.png:alternate",
                    evidence_bytes,
                    "image/png",
                )
            },
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(
            upload.json()["filename"],
            "evidence.png:alternate",
        )
        evidence_url = upload.json()["url"]
        stored_evidence = list(
            (self.data_dir / "evidence" / finding_id).iterdir()
        )
        self.assertEqual(len(stored_evidence), 1)
        self.assertEqual(stored_evidence[0].suffix, ".png")
        self.assertNotIn(":", stored_evidence[0].name)

        downloaded_evidence = self.client.get(evidence_url, headers=headers)
        self.assertEqual(downloaded_evidence.status_code, 200)
        self.assertEqual(downloaded_evidence.content, evidence_bytes)
        self.assertEqual(
            downloaded_evidence.headers["x-content-type-options"],
            "nosniff",
        )
        self.assertEqual(
            downloaded_evidence.headers["content-security-policy"],
            "default-src 'none'; sandbox",
        )
        invalid_json_evidence = self.client.post(
            f"/api/engagements/{engagement_id}/findings/{finding_id}/evidence",
            headers=headers,
            files={"file": ("capture.har", b"not-json", "application/octet-stream")},
        )
        self.assertEqual(invalid_json_evidence.status_code, 415, invalid_json_evidence.text)
        har_bytes = json.dumps({"log": {"version": "1.2", "entries": []}}).encode("utf-8")
        har_upload = self.client.post(
            f"/api/engagements/{engagement_id}/findings/{finding_id}/evidence",
            headers=headers,
            files={"file": ("capture.har", har_bytes, "application/octet-stream")},
        )
        self.assertEqual(har_upload.status_code, 200, har_upload.text)
        self.assertEqual(har_upload.json()["content_type"], "application/har+json")
        har_download = self.client.get(har_upload.json()["url"], headers=headers)
        self.assertEqual(har_download.content, har_bytes)
        self.assertIn("attachment", har_download.headers["content-disposition"])
        self.assertEqual(
            self.client.delete(
                f"/api/engagements/{engagement_id}/findings/{finding_id}/evidence/{har_upload.json()['id']}",
                headers=headers,
            ).status_code,
            204,
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
        remaining_findings = self.client.get(
            f"/api/engagements/{engagement_id}/findings",
            headers=headers,
        )
        self.assertNotIn(
            bulk_cleanup_id,
            {item["id"] for item in remaining_findings.json()},
        )
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM finding_history WHERE finding_id = ?",
                    (bulk_cleanup_id,),
                ).fetchone()[0],
                0,
            )

        direct_cleanup_finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            headers=headers,
            json={"title": "Direct cleanup finding", "severity": "info"},
        )
        self.assertEqual(
            direct_cleanup_finding.status_code,
            201,
            direct_cleanup_finding.text,
        )
        direct_cleanup_id = direct_cleanup_finding.json()["id"]
        direct_delete = self.client.delete(
            f"/api/engagements/{engagement_id}/findings/{direct_cleanup_id}",
            headers=headers,
        )
        self.assertEqual(direct_delete.status_code, 204, direct_delete.text)
        remaining_findings = self.client.get(
            f"/api/engagements/{engagement_id}/findings",
            headers=headers,
        )
        self.assertNotIn(
            direct_cleanup_id,
            {item["id"] for item in remaining_findings.json()},
        )
        with closing(sqlite3.connect(self.database_path)) as connection:
            history_rows = connection.execute(
                "SELECT action, source FROM finding_history WHERE finding_id = ?",
                (direct_cleanup_id,),
            ).fetchall()
        self.assertEqual(
            history_rows,
            [],
        )

        report_ai_preflight = self.client.get(
            f"/api/engagements/{engagement_id}/reports/ai-preflight",
            headers=headers,
        )
        self.assertEqual(
            report_ai_preflight.status_code,
            200,
            report_ai_preflight.text,
        )
        report_ai_preview = report_ai_preflight.json()
        self.assertTrue(report_ai_preview["ready"])
        self.assertGreater(report_ai_preview["context_chars"], 0)
        self.assertLessEqual(
            report_ai_preview["context_chars"],
            report_ai_preview["max_context_chars"],
        )
        self.assertEqual(
            report_ai_preview["finding_count"],
            len(remaining_findings.json()),
        )
        self.assertTrue(report_ai_preview["redaction_enabled"])
        self.assertEqual(
            self.client.get(
                "/api/engagements/missing/reports/ai-preflight",
                headers=headers,
            ).status_code,
            404,
        )

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

        missing_template_report = self.client.post(
            f"/api/engagements/{engagement_id}/reports",
            headers=headers,
            params={"format": "docx", "template_id": str(uuid.uuid4())},
        )
        self.assertEqual(missing_template_report.status_code, 404)

        report_template = self.client.post(
            "/api/report-templates",
            headers=headers,
            data={
                "name": "Client delivery template",
                "company_name": "Example Client",
                "is_default": "false",
            },
        )
        self.assertEqual(report_template.status_code, 201, report_template.text)

        docx_report = self.client.post(
            f"/api/engagements/{engagement_id}/reports",
            headers=headers,
            params={
                "format": "docx",
                "template_id": report_template.json()["id"],
            },
        )
        self.assertEqual(docx_report.status_code, 201, docx_report.text)
        self.assertEqual(
            docx_report.json()["template_used"],
            "Client delivery template",
        )
        docx_download = self.client.get(
            f"/api/reports/{docx_report.json()['id']}/download",
            headers=headers,
        )
        self.assertEqual(docx_download.status_code, 200)
        self.assertTrue(docx_download.content.startswith(b"PK"))
        deleted_docx = self.client.delete(
            f"/api/reports/{docx_report.json()['id']}",
            headers=headers,
        )
        self.assertEqual(deleted_docx.status_code, 204, deleted_docx.text)
        self.assertEqual(
            self.client.get(
                f"/api/reports/{docx_report.json()['id']}/download",
                headers=headers,
            ).status_code,
            404,
        )

        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "INSERT INTO attack_paths (id, engagement_id, name, description, "
                "steps, risk_level, narrative, mitre_techniques) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    engagement_id,
                    "Validated local chain",
                    "A bounded attack chain.",
                    json.dumps([{
                        "order": 1,
                        "title": "Initial access",
                        "finding_id": finding_id,
                    }]),
                    "high",
                    "The analyst-validated narrative.",
                    json.dumps([{
                        "technique_id": "T1190",
                        "technique_name": "Exploit Public-Facing Application",
                    }]),
                ),
            )
            connection.commit()

        export = self.client.get(
            f"/api/engagements/{engagement_id}/export",
            headers=headers,
        )
        self.assertEqual(export.status_code, 200)
        exported = export.json()
        self.assertEqual(exported["engagement"]["name"], "Release Candidate Assessment")
        self.assertEqual(exported["findings"][0]["title"], "Outdated service")
        self.assertEqual(
            exported["attack_paths"][0]["narrative"],
            "The analyst-validated narrative.",
        )
        self.assertEqual(exported["findings"][0]["portable_id"], finding_id)
        self.assertEqual(
            exported["attack_paths"][0]["mitre_techniques"][0]["technique_id"],
            "T1190",
        )
        self.assertEqual(
            exported["engagement_narrative"],
            {
                "narrative": "Validated local narrative",
                "citations": [f"FINDING:{finding_id}"],
            },
        )

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
        invalid_attack_path_export = json.loads(json.dumps(exported))
        invalid_attack_path_export["attack_paths"] = [
            {
                "name": "Malformed path",
                "steps": "steps must be a list",
                "risk_level": "high",
            }
        ]
        rejected_attack_path_import = self.client.post(
            "/api/engagements/import",
            headers=headers,
            files={
                "file": (
                    "invalid-attack-path.json",
                    json.dumps(invalid_attack_path_export).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(
            rejected_attack_path_import.status_code,
            422,
            rejected_attack_path_import.text,
        )
        after_rejected_attack_path = self.client.get(
            "/api/engagements",
            headers=headers,
        )
        self.assertEqual(len(after_rejected_attack_path.json()), 1)

        imported = self.client.post(
            "/api/engagements/import",
            headers=headers,
            files={
                "file": (
                    "engagement.json",
                    json.dumps({**exported, "version": "1.0"}).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["findings_imported"], 1)
        self.assertEqual(imported.json()["attack_paths_imported"], 1)
        imported_paths = self.client.get(
            f"/api/engagements/{imported.json()['id']}/attack-paths",
            headers=headers,
        )
        self.assertEqual(imported_paths.status_code, 200, imported_paths.text)
        self.assertEqual(
            imported_paths.json()[0]["narrative"],
            "The analyst-validated narrative.",
        )
        imported_findings_response = self.client.get(
            f"/api/engagements/{imported.json()['id']}/findings",
            headers=headers,
        )
        self.assertEqual(
            imported_paths.json()[0]["steps"][0]["finding_id"],
            imported_findings_response.json()[0]["id"],
        )
        self.assertNotEqual(
            imported_paths.json()[0]["steps"][0]["finding_id"],
            finding_id,
        )
        self.assertEqual(
            imported_paths.json()[0]["mitre_techniques"][0]["technique_id"],
            "T1190",
        )
        imported_narrative = self.client.get(
            f"/api/engagements/{imported.json()['id']}/narrative/full",
            headers=headers,
        )
        self.assertEqual(imported_narrative.status_code, 200, imported_narrative.text)
        self.assertEqual(
            imported_narrative.json(),
            {
                "narrative": "Validated local narrative",
                "citations": [
                    f"FINDING:{imported_findings_response.json()[0]['id']}"
                ],
            },
        )

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
        self.assertTrue(backup.json()["valid"])
        self.assertGreaterEqual(backup.json()["file_count"], 1)
        backup_list = self.client.get("/api/system/backups", headers=headers)
        self.assertEqual(backup_list.status_code, 200, backup_list.text)
        self.assertIn(
            backup_name,
            {item["filename"] for item in backup_list.json()},
        )
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
        invalid_name = "breachwright-backup-corrupt.zip"
        invalid_path = self.data_dir / "backups" / invalid_name
        invalid_path.write_text("not a zip archive", encoding="utf-8")
        backup_list = self.client.get("/api/system/backups", headers=headers)
        self.assertEqual(backup_list.status_code, 200, backup_list.text)
        invalid = next(
            item for item in backup_list.json() if item["filename"] == invalid_name
        )
        self.assertFalse(invalid["valid"])
        self.assertIn("cannot be read", invalid["error"])
        invalid_download = self.client.get(
            f"/api/system/backups/{invalid_name}",
            headers=headers,
        )
        self.assertEqual(invalid_download.status_code, 409, invalid_download.text)
        invalid_delete = self.client.delete(
            f"/api/system/backups/{invalid_name}",
            headers=headers,
        )
        self.assertEqual(invalid_delete.status_code, 204, invalid_delete.text)
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

        activity = self.client.get(
            f"/api/engagements/{engagement_id}/activity?limit=3",
            headers=headers,
        )
        self.assertEqual(activity.status_code, 200, activity.text)
        self.assertLessEqual(activity.json()["count"], 3)
        self.assertEqual(activity.json()["limit"], 3)
        self.assertTrue(
            {"finding", "scan", "report"}
            & {event["kind"] for event in activity.json()["events"]}
        )
        self.assertTrue(
            all(event["tab"] for event in activity.json()["events"])
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
        self.assertEqual(
            self.client.delete(
                f"/api/engagements/{imported.json()['id']}",
                headers=headers,
            ).status_code,
            204,
        )

    def test_reviewed_ai_draft_preserves_provenance(self):
        created_engagement = self.client.post(
            "/api/engagements",
            json={
                "name": "AI Review Workflow",
                "client_name": "Local Test",
                "scope": "10.20.30.0/24",
            },
        )
        self.assertEqual(created_engagement.status_code, 201, created_engagement.text)
        engagement_id = created_engagement.json()["id"]
        draft_id = str(uuid.uuid4())
        evidence_refs = [
            {
                "id": "CF-0001-E01",
                "scan_id": "scan-1",
                "filename": "sanitized.nessus",
                "scan_type": "nessus",
                "tool": "nessus",
                "host": "10.20.30.10",
                "port": 445,
                "cve": None,
                "plugin_id": "57608",
                "excerpt": "SMB signing is not required.",
                "correlation_confidence": 0.8,
            }
        ]
        with closing(sqlite3.connect(self.database_path)) as connection:
            owner_id = connection.execute(
                "SELECT id FROM users ORDER BY created_at, id LIMIT 1"
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO ai_finding_drafts ("
                "id, engagement_id, target_finding_id, operation, status, title, "
                "description, severity, cvss_score, affected_hosts, evidence, "
                "remediation, evidence_refs, confidence, provider, prompt_version, "
                "created_by) VALUES (?, ?, NULL, 'create', 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    draft_id,
                    engagement_id,
                    "SMB Signing Not Required",
                    "The service permits unsigned SMB traffic.",
                    "medium",
                    5.3,
                    "10.20.30.10",
                    "SMB signing is not required.",
                    "Require SMB signing.",
                    json.dumps(evidence_refs),
                    0.8,
                    "Fake (offline)",
                    "analysis-v2-evidence-grounded",
                    owner_id,
                ),
            )
            connection.commit()

        listed = self.client.get(
            f"/api/engagements/{engagement_id}/ai-drafts"
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()[0]["evidence_refs"][0]["id"], "CF-0001-E01")

        accepted = self.client.post(
            f"/api/engagements/{engagement_id}/ai-drafts/{draft_id}/accept",
            json={"severity": "high", "cvss_score": 8.1},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["severity"], "high")
        self.assertTrue(accepted.json()["ai_inference"])
        self.assertEqual(accepted.json()["source"], "ai_reviewed")
        self.assertEqual(
            accepted.json()["evidence_refs"][0]["filename"],
            "sanitized.nessus",
        )
        self.assertEqual(
            self.client.post(
                f"/api/engagements/{engagement_id}/ai-drafts/{draft_id}/accept"
            ).status_code,
            409,
        )

        exported = self.client.get(f"/api/engagements/{engagement_id}/export")
        self.assertEqual(exported.status_code, 200, exported.text)
        exported_finding = exported.json()["findings"][0]
        self.assertTrue(exported_finding["ai_inference"])
        self.assertEqual(exported_finding["source"], "ai_reviewed")
        self.assertEqual(exported_finding["evidence_refs"][0]["id"], "CF-0001-E01")

        imported = self.client.post(
            "/api/engagements/import",
            files={"file": ("ai-reviewed.json", exported.content, "application/json")},
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        imported_findings = self.client.get(
            f"/api/engagements/{imported.json()['id']}/findings"
        )
        self.assertEqual(imported_findings.status_code, 200, imported_findings.text)
        imported_finding = imported_findings.json()[0]
        self.assertTrue(imported_finding["ai_inference"])
        self.assertEqual(imported_finding["source"], "ai_reviewed")
        self.assertEqual(imported_finding["ai_confidence"], 0.8)
        self.assertEqual(
            imported_finding["evidence_refs"][0]["id"],
            "CF-0001-E01",
        )
        self.assertEqual(
            self.client.delete(f"/api/engagements/{imported.json()['id']}").status_code,
            204,
        )

        deleted = self.client.delete(f"/api/engagements/{engagement_id}")
        self.assertEqual(deleted.status_code, 204, deleted.text)

    def test_repeatable_assessment_history_readiness_and_interchange(self):
        created = self.client.post(
            "/api/engagements",
            json={
                "name": "Repeatable Assessment",
                "client_name": "Local Test",
                "scope": "https://app.example.test",
                "template_key": "web",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        engagement_id = created.json()["id"]
        self.assertEqual(created.json()["template_key"], "web")
        checklist = self.client.get(f"/api/engagements/{engagement_id}/checklists")
        self.assertEqual(checklist.status_code, 200, checklist.text)
        self.assertGreater(len(checklist.json()), 0)
        self.assertTrue(all(item["methodology"] == "owasp_top10" for item in checklist.json()))
        empty_inventory = self.client.get(f"/api/engagements/{engagement_id}/assets")
        self.assertEqual(empty_inventory.status_code, 200, empty_inventory.text)
        self.assertIsNone(empty_inventory.json()["snapshot"])
        self.assertEqual(empty_inventory.json()["summary"]["assets"], 0)
        completed_checklist_item = checklist.json()[0]
        checklist_update = self.client.put(
            f"/api/engagements/{engagement_id}/checklists/{completed_checklist_item['id']}",
            json={"status": "done", "notes": "Verified during the baseline assessment."},
        )
        self.assertEqual(checklist_update.status_code, 200, checklist_update.text)

        finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            json={
                "title": "Administrative endpoint exposed",
                "description": "Authorization: Bearer top-secret\nAdministrative route exposed.",
                "severity": "high",
                "cvss_score": 0,
                "affected_hosts": "https://app.example.test/admin",
                "retest_status": "retest_needed",
                "retest_due_date": "2020-01-02",
            },
        )
        self.assertEqual(finding.status_code, 201, finding.text)
        finding_id = finding.json()["id"]
        queue = self.client.get(f"/api/engagements/{engagement_id}/retest-queue")
        self.assertEqual(queue.status_code, 200, queue.text)
        self.assertEqual(queue.json()[0]["id"], finding_id)
        self.assertTrue(queue.json()[0]["overdue"])
        urgent_finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            json={
                "title": "Urgent retest ordering check",
                "severity": "critical",
                "retest_status": "retest_needed",
                "retest_due_date": "2020-01-02",
            },
        )
        self.assertEqual(urgent_finding.status_code, 201, urgent_finding.text)
        ordered_findings = self.client.get(
            f"/api/engagements/{engagement_id}/findings"
        )
        self.assertEqual(
            [item["severity"] for item in ordered_findings.json()[:2]],
            ["critical", "high"],
        )
        ordered_queue = self.client.get(
            f"/api/engagements/{engagement_id}/retest-queue"
        )
        self.assertEqual(
            [item["severity"] for item in ordered_queue.json()[:2]],
            ["critical", "high"],
        )
        self.assertEqual(
            self.client.delete(
                f"/api/engagements/{engagement_id}/findings/{urgent_finding.json()['id']}"
            ).status_code,
            204,
        )
        retest_overview = self.client.get(
            f"/api/engagements/{engagement_id}/retest-overview"
        )
        self.assertEqual(retest_overview.status_code, 200, retest_overview.text)
        self.assertEqual(retest_overview.json()["summary"]["overdue"], 1)
        self.assertEqual(retest_overview.json()["overdue"][0]["id"], finding_id)

        readiness = self.client.get(f"/api/engagements/{engagement_id}/report-readiness")
        self.assertEqual(readiness.status_code, 200, readiness.text)
        self.assertFalse(readiness.json()["ready"])
        self.assertEqual(len(readiness.json()["blockers"]), 2)
        attachment = self.client.post(
            f"/api/engagements/{engagement_id}/findings/{finding_id}/evidence",
            files={"file": ("admin-proof.png", b"\x89PNG\r\n\x1a\nproof", "image/png")},
        )
        self.assertEqual(attachment.status_code, 200, attachment.text)
        readiness = self.client.get(f"/api/engagements/{engagement_id}/report-readiness")
        self.assertEqual(
            [blocker["code"] for blocker in readiness.json()["blockers"]],
            ["high_risk_missing_remediation"],
        )
        updated = self.client.put(
            f"/api/engagements/{engagement_id}/findings/{finding_id}",
            json={
                "remediation": "Require authorization for the administrative route.",
                "retest_status": "remediated",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        history = self.client.get(
            f"/api/engagements/{engagement_id}/findings/{finding_id}/history"
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual([entry["action"] for entry in history.json()], ["updated", "created"])
        self.assertIn("remediation", history.json()[0]["changes"])
        self.assertIn("retest_status", history.json()[0]["changes"])
        retest_overview = self.client.get(
            f"/api/engagements/{engagement_id}/retest-overview"
        )
        self.assertEqual(retest_overview.status_code, 200, retest_overview.text)
        self.assertEqual(retest_overview.json()["summary"]["overdue"], 0)
        self.assertEqual(retest_overview.json()["summary"]["recently_resolved"], 1)
        self.assertEqual(
            retest_overview.json()["recently_resolved"][0]["id"],
            finding_id,
        )
        readiness = self.client.get(f"/api/engagements/{engagement_id}/report-readiness")
        self.assertTrue(readiness.json()["ready"])
        self.assertGreater(readiness.json()["score"], 0)

        nuclei_a = json.dumps({
            "template-id": "exposed-admin-panel",
            "host": "app.example.test",
            "matched-at": "https://app.example.test/admin",
            "info": {"name": "Exposed Admin Panel", "severity": "high"},
        })
        nuclei_b = json.dumps({
            "template-id": "missing-csp",
            "host": "app.example.test",
            "matched-at": "https://app.example.test/",
            "info": {"name": "Missing CSP", "severity": "medium"},
        })

        def upload(name, content):
            response = self.client.post(
                f"/api/engagements/{engagement_id}/upload-scan?scan_type=nuclei",
                files={"file": (name, content.encode("utf-8"), "application/x-ndjson")},
            )
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()["id"]

        scan_a1 = upload("baseline.jsonl", nuclei_a)
        snapshot1 = self.client.post(
            f"/api/engagements/{engagement_id}/scan-snapshots",
            json={"label": "Baseline", "scan_ids": [scan_a1]},
        )
        self.assertEqual(snapshot1.status_code, 201, snapshot1.text)
        self.assertEqual(snapshot1.json()["counts"]["new"], 1)

        scan_b = upload("retest-one.jsonl", nuclei_b)
        snapshot2 = self.client.post(
            f"/api/engagements/{engagement_id}/scan-snapshots",
            json={"label": "Retest 1", "scan_ids": [scan_b]},
        )
        self.assertEqual(snapshot2.status_code, 201, snapshot2.text)
        self.assertEqual(snapshot2.json()["counts"], {"new": 1, "persistent": 0, "resolved": 1, "regressed": 0})

        scan_a2 = upload("retest-two.jsonl", nuclei_a + "\n" + nuclei_b)
        pending_snapshot_readiness = self.client.get(
            f"/api/engagements/{engagement_id}/report-readiness"
        )
        self.assertIn(
            "unversioned_scans",
            {
                warning["code"]
                for warning in pending_snapshot_readiness.json()["warnings"]
            },
        )
        self.assertEqual(
            pending_snapshot_readiness.json()["summary"]["unversioned_scans"],
            1,
        )
        snapshot3 = self.client.post(
            f"/api/engagements/{engagement_id}/scan-snapshots",
            json={"label": "Retest 2", "scan_ids": [scan_a2]},
        )
        self.assertEqual(snapshot3.status_code, 201, snapshot3.text)
        self.assertEqual(snapshot3.json()["counts"], {"new": 0, "persistent": 1, "resolved": 0, "regressed": 1})
        current_readiness = self.client.get(
            f"/api/engagements/{engagement_id}/report-readiness"
        )
        self.assertEqual(
            current_readiness.json()["summary"]["unversioned_scans"],
            0,
        )
        replay = self.client.get(
            f"/api/engagements/{engagement_id}/scan-snapshots/{snapshot3.json()['snapshot']['id']}/comparison"
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["counts"], snapshot3.json()["counts"])
        inventory = self.client.get(f"/api/engagements/{engagement_id}/assets")
        self.assertEqual(inventory.status_code, 200, inventory.text)
        self.assertEqual(inventory.json()["snapshot"]["label"], "Retest 2")
        self.assertEqual(inventory.json()["summary"]["assets"], 1)
        self.assertEqual(inventory.json()["summary"]["vulnerabilities"], 2)
        self.assertEqual(inventory.json()["summary"]["services"], 0)
        self.assertEqual(inventory.json()["summary"]["linked_findings"], 1)
        asset = inventory.json()["assets"][0]
        self.assertEqual(asset["host"], "app.example.test")
        self.assertEqual(asset["status"], "regressed")
        self.assertEqual(asset["highest_severity"], "high")
        self.assertEqual(asset["snapshot_count"], 3)
        self.assertEqual(asset["finding_count"], 1)
        self.assertFalse(asset["details_limited"])
        self.assertEqual(asset["findings"][0]["id"], finding_id)
        self.assertEqual(asset["findings"][0]["evidence_attachment_count"], 1)
        finding_search = self.client.get(
            f"/api/engagements/{engagement_id}/search",
            params={"q": "administrative endpoint"},
        )
        self.assertEqual(finding_search.status_code, 200, finding_search.text)
        self.assertIn("finding", {item["type"] for item in finding_search.json()["results"]})
        evidence_search = self.client.get(
            f"/api/engagements/{engagement_id}/search",
            params={"q": "admin-proof"},
        )
        self.assertEqual(evidence_search.status_code, 200, evidence_search.text)
        self.assertEqual(evidence_search.json()["results"][0]["type"], "evidence")
        asset_search = self.client.get(
            f"/api/engagements/{engagement_id}/search",
            params={"q": "app.example.test"},
        )
        self.assertEqual(asset_search.status_code, 200, asset_search.text)
        self.assertIn("asset", {item["type"] for item in asset_search.json()["results"]})
        short_search = self.client.get(
            f"/api/engagements/{engagement_id}/search",
            params={"q": "a"},
        )
        self.assertEqual(short_search.status_code, 422)
        literal_wildcard_search = self.client.get(
            f"/api/engagements/{engagement_id}/search",
            params={"q": "%_"},
        )
        self.assertEqual(literal_wildcard_search.status_code, 200, literal_wildcard_search.text)
        self.assertEqual(literal_wildcard_search.json()["count"], 0)

        sarif = self.client.get(f"/api/engagements/{engagement_id}/findings.sarif")
        self.assertEqual(sarif.status_code, 200, sarif.text)
        self.assertEqual(sarif.json()["version"], "2.1.0")
        self.assertEqual(len(sarif.json()["runs"][0]["results"]), 1)
        self.assertEqual(
            sarif.json()["runs"][0]["results"][0]["ruleId"],
            f"BW-{finding_id}",
        )
        self.assertIn("attachment", sarif.headers["content-disposition"])
        self.assertIn("top-secret", sarif.text)
        redacted_sarif = self.client.get(
            f"/api/engagements/{engagement_id}/findings.sarif",
            params={"redact_sensitive": "true"},
        )
        self.assertEqual(redacted_sarif.status_code, 200, redacted_sarif.text)
        self.assertNotIn("top-secret", redacted_sarif.text)
        self.assertIn("[REDACTED]", redacted_sarif.text)
        self.assertIn("redacted", redacted_sarif.headers["content-disposition"])
        sarif_upload = self.client.post(
            f"/api/engagements/{engagement_id}/upload-scan?scan_type=sarif",
            files={"file": ("breachwright.sarif", sarif.content, "application/sarif+json")},
        )
        self.assertEqual(sarif_upload.status_code, 200, sarif_upload.text)
        sarif_snapshot = self.client.post(
            f"/api/engagements/{engagement_id}/scan-snapshots",
            json={"label": "SARIF round trip", "scan_ids": [sarif_upload.json()["id"]]},
        )
        self.assertEqual(sarif_snapshot.status_code, 201, sarif_snapshot.text)
        self.assertEqual(sarif_snapshot.json()["snapshot"]["observation_count"], 1)

        completed = self.client.put(
            f"/api/engagements/{engagement_id}",
            json={"status": "completed"},
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        portable = self.client.get(f"/api/engagements/{engagement_id}/export")
        self.assertEqual(portable.status_code, 200, portable.text)
        self.assertEqual(portable.json()["version"], "1.1")
        self.assertEqual(portable.json()["engagement"]["template_key"], "web")
        self.assertEqual(portable.json()["engagement"]["status"], "completed")
        self.assertEqual(portable.json()["findings"][0]["cvss_score"], 0.0)
        self.assertEqual(portable.json()["findings"][0]["retest_due_date"], "2020-01-02")
        self.assertEqual(
            [item["action"] for item in portable.json()["findings"][0]["history"]],
            ["created", "updated"],
        )
        self.assertEqual(len(portable.json()["checklists"]), len(checklist.json()))
        self.assertEqual(len(portable.json()["scan_snapshots"]), 4)
        exported_checklist_item = next(
            item
            for item in portable.json()["checklists"]
            if item["item"] == completed_checklist_item["item"]
        )
        self.assertEqual(exported_checklist_item["status"], "done")
        self.assertEqual(
            exported_checklist_item["notes"],
            "Verified during the baseline assessment.",
        )
        future_export = portable.json()
        future_export["version"] = "2.0"
        rejected_future = self.client.post(
            "/api/engagements/import",
            files={
                "file": (
                    "future-export.json",
                    json.dumps(future_export).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(rejected_future.status_code, 422, rejected_future.text)
        invalid_checklist_export = portable.json()
        invalid_checklist_export["checklists"][0]["status"] = "invalid"
        rejected_checklist = self.client.post(
            "/api/engagements/import",
            files={
                "file": (
                    "invalid-checklist-export.json",
                    json.dumps(invalid_checklist_export).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(rejected_checklist.status_code, 422, rejected_checklist.text)
        invalid_snapshot_export = portable.json()
        invalid_snapshot_export["scan_snapshots"][0]["observations"][0]["fingerprint"] = "not-a-fingerprint"
        rejected_snapshot = self.client.post(
            "/api/engagements/import",
            files={
                "file": (
                    "invalid-snapshot-export.json",
                    json.dumps(invalid_snapshot_export).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(rejected_snapshot.status_code, 422, rejected_snapshot.text)
        self.assertEqual(len(self.client.get("/api/engagements").json()), 1)
        invalid_history_export = portable.json()
        invalid_history_export["findings"][0]["history"][0]["changes"] = []
        rejected_history = self.client.post(
            "/api/engagements/import",
            files={
                "file": (
                    "invalid-history-export.json",
                    json.dumps(invalid_history_export).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(rejected_history.status_code, 422, rejected_history.text)
        self.assertEqual(len(self.client.get("/api/engagements").json()), 1)
        portable_with_tied_times = portable.json()
        tied_time = portable_with_tied_times["scan_snapshots"][0]["created_at"]
        for item in portable_with_tied_times["scan_snapshots"]:
            item["created_at"] = tied_time
        imported = self.client.post(
            "/api/engagements/import",
            files={
                "file": (
                    "repeatable-export.json",
                    json.dumps(portable_with_tied_times).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(
            imported.json()["checklist_items_imported"],
            len(checklist.json()),
        )
        self.assertEqual(imported.json()["scan_snapshots_imported"], 4)
        self.assertEqual(imported.json()["finding_history_items_imported"], 2)
        imported_id = imported.json()["id"]
        imported_engagement = self.client.get(f"/api/engagements/{imported_id}")
        self.assertEqual(imported_engagement.json()["template_key"], "web")
        self.assertEqual(imported_engagement.json()["status"], "completed")
        imported_findings = self.client.get(f"/api/engagements/{imported_id}/findings")
        self.assertEqual(imported_findings.json()[0]["source"], "manual")
        self.assertEqual(imported_findings.json()[0]["retest_due_date"], "2020-01-02")
        imported_checklist = self.client.get(
            f"/api/engagements/{imported_id}/checklists"
        )
        imported_completed_item = next(
            item
            for item in imported_checklist.json()
            if item["item"] == completed_checklist_item["item"]
        )
        self.assertEqual(imported_completed_item["status"], "done")
        self.assertEqual(
            imported_completed_item["notes"],
            "Verified during the baseline assessment.",
        )
        imported_snapshots = self.client.get(
            f"/api/engagements/{imported_id}/scan-snapshots"
        )
        self.assertEqual(imported_snapshots.status_code, 200, imported_snapshots.text)
        self.assertEqual(
            {item["label"] for item in imported_snapshots.json()},
            {"Baseline", "Retest 1", "Retest 2", "SARIF round trip"},
        )
        imported_retest_two = next(
            item for item in imported_snapshots.json() if item["label"] == "Retest 2"
        )
        imported_comparison = self.client.get(
            f"/api/engagements/{imported_id}/scan-snapshots/{imported_retest_two['id']}/comparison"
        )
        self.assertEqual(imported_comparison.status_code, 200, imported_comparison.text)
        self.assertEqual(imported_comparison.json()["counts"], snapshot3.json()["counts"])
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "UPDATE scan_snapshots SET parser_version = ? WHERE id = ?",
                ("structured-v0", imported_snapshots.json()[0]["id"]),
            )
            connection.commit()
        imported_readiness = self.client.get(
            f"/api/engagements/{imported_id}/report-readiness"
        )
        self.assertIn(
            "mixed_snapshot_parsers",
            {item["code"] for item in imported_readiness.json()["warnings"]},
        )
        imported_latest_comparison = self.client.get(
            f"/api/engagements/{imported_id}/scan-snapshots/{imported_snapshots.json()[0]['id']}/comparison"
        )
        self.assertEqual(
            imported_latest_comparison.json()["warnings"][0]["code"],
            "mixed_snapshot_parsers",
        )
        imported_history = self.client.get(
            f"/api/engagements/{imported_id}/findings/{imported_findings.json()[0]['id']}/history"
        )
        self.assertEqual(
            [item["action"] for item in imported_history.json()],
            ["updated", "created"],
        )
        self.assertEqual(self.client.delete(f"/api/engagements/{imported_id}").status_code, 204)

        deleted = self.client.delete(f"/api/engagements/{engagement_id}")
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertEqual(
            self.client.get(f"/api/engagements/{engagement_id}/scan-snapshots").status_code,
            404,
        )
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM scan_snapshots WHERE engagement_id = ?", (engagement_id,)).fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM finding_history WHERE engagement_id = ?", (engagement_id,)).fetchone()[0], 0)

    def test_asset_inventory_preserves_host_aliases_services_and_operating_system(self):
        created = self.client.post(
            "/api/engagements",
            json={"name": "Asset Inventory", "client_name": "Local Test"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        engagement_id = created.json()["id"]
        finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            json={
                "title": "Administrative interface exposed",
                "severity": "high",
                "affected_hosts": "https://web01.example.test/admin",
            },
        )
        self.assertEqual(finding.status_code, 201, finding.text)
        additional_ports = "".join(
            f'<port protocol="tcp" portid="{port}"><state state="open"/>'
            f'<service name="http" product="test-service-{port}"/></port>'
            for port in range(10000, 10100)
        )
        nmap_xml = f"""<?xml version="1.0"?>
<nmaprun><host><status state="up"/><address addr="192.0.2.10" addrtype="ipv4"/>
<hostnames><hostname name="web01.example.test" type="PTR"/></hostnames>
<ports><port protocol="tcp" portid="443"><state state="open"/>
<service name="https" product="nginx" version="1.26"/>
<script id="smb2-security-mode" output="Message signing enabled but not required"/></port>{additional_ports}</ports>
<os><osmatch name="Linux 6.x" accuracy="96"/></os></host></nmaprun>"""
        scan = self.client.post(
            f"/api/engagements/{engagement_id}/upload-scan?scan_type=nmap",
            files={"file": ("inventory.xml", nmap_xml.encode("utf-8"), "application/xml")},
        )
        self.assertEqual(scan.status_code, 200, scan.text)
        snapshot = self.client.post(
            f"/api/engagements/{engagement_id}/scan-snapshots",
            json={"label": "Discovery baseline", "scan_ids": [scan.json()["id"]]},
        )
        self.assertEqual(snapshot.status_code, 201, snapshot.text)
        self.assertEqual(snapshot.json()["snapshot"]["parser_version"], "structured-v2")
        inventory = self.client.get(f"/api/engagements/{engagement_id}/assets")
        self.assertEqual(inventory.status_code, 200, inventory.text)
        self.assertEqual(inventory.json()["summary"]["services"], 101)
        self.assertEqual(inventory.json()["summary"]["observation_limit_per_type"], 100)
        asset = inventory.json()["assets"][0]
        self.assertEqual(asset["host"], "192.0.2.10")
        self.assertEqual(asset["aliases"], ["web01.example.test"])
        self.assertEqual(asset["operating_systems"], ["Linux 6.x"])
        self.assertEqual(asset["findings"][0]["id"], finding.json()["id"])
        self.assertEqual(asset["services"][0]["evidence_ref"]["product"], "nginx")
        self.assertEqual(asset["service_count"], 101)
        self.assertEqual(len(asset["services"]), 100)
        self.assertTrue(asset["details_limited"])
        self.assertEqual(asset["vulnerability_count"], 1)
        observation = asset["vulnerabilities"][0]
        promoted = self.client.post(
            f"/api/engagements/{engagement_id}/scan-snapshots/{snapshot.json()['snapshot']['id']}/observations/{observation['fingerprint']}/finding"
        )
        self.assertEqual(promoted.status_code, 201, promoted.text)
        self.assertEqual(promoted.json()["source"], "scan_reviewed")
        self.assertFalse(promoted.json()["ai_inference"])
        self.assertEqual(
            promoted.json()["evidence_refs"][0]["scan_observation_fingerprint"],
            observation["fingerprint"],
        )
        duplicate = self.client.post(
            f"/api/engagements/{engagement_id}/scan-snapshots/{snapshot.json()['snapshot']['id']}/observations/{observation['fingerprint']}/finding"
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        refreshed_inventory = self.client.get(f"/api/engagements/{engagement_id}/assets")
        accepted_observation = refreshed_inventory.json()["assets"][0]["vulnerabilities"][0]
        self.assertEqual(accepted_observation["finding_id"], promoted.json()["id"])
        promoted_history = self.client.get(
            f"/api/engagements/{engagement_id}/findings/{promoted.json()['id']}/history"
        )
        self.assertEqual(promoted_history.json()[0]["action"], "scan_observation_accepted")
        alias_search = self.client.get(
            f"/api/engagements/{engagement_id}/search",
            params={"q": "web01.example.test"},
        )
        self.assertEqual(alias_search.status_code, 200, alias_search.text)
        self.assertIn("asset", {item["type"] for item in alias_search.json()["results"]})
        asset_result = next(item for item in alias_search.json()["results"] if item["type"] == "asset")
        self.assertIn("web01.example.test", asset_result["snippet"])
        self.assertNotIn('"hostnames"', asset_result["snippet"])
        self.assertEqual(self.client.delete(f"/api/engagements/{engagement_id}").status_code, 204)

    def test_all_engagement_templates_create_their_methodology(self):
        expected = {
            "web": "owasp_top10",
            "api": "owasp_api_top10",
            "external": "network_pentest",
            "internal": "network_pentest",
            "active_directory": "ptes",
            "cloud": "nist_800_115",
        }
        for template_key, methodology in expected.items():
            with self.subTest(template=template_key):
                created = self.client.post(
                    "/api/engagements",
                    json={
                        "name": f"{template_key} template check",
                        "client_name": "Local Test",
                        "template_key": template_key,
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                engagement_id = created.json()["id"]
                checklist = self.client.get(
                    f"/api/engagements/{engagement_id}/checklists"
                )
                self.assertEqual(checklist.status_code, 200, checklist.text)
                self.assertGreater(len(checklist.json()), 0)
                self.assertEqual(
                    {item["methodology"] for item in checklist.json()},
                    {methodology},
                )
                if template_key == "api":
                    self.assertEqual(len(checklist.json()), 10)
                    self.assertEqual(
                        {
                            item["category"].split(":", 1)[0]
                            for item in checklist.json()
                        },
                        {f"API{index}" for index in range(1, 11)},
                    )
                if template_key == "web":
                    self.assertEqual(
                        {item["category"] for item in checklist.json()},
                        {
                            "A01:2025 Broken Access Control",
                            "A02:2025 Security Misconfiguration",
                            "A03:2025 Software Supply Chain Failures",
                            "A04:2025 Cryptographic Failures",
                            "A05:2025 Injection",
                            "A06:2025 Insecure Design",
                            "A07:2025 Authentication Failures",
                            "A08:2025 Software or Data Integrity Failures",
                            "A09:2025 Security Logging and Alerting Failures",
                            "A10:2025 Mishandling of Exceptional Conditions",
                        },
                    )
                    self.assertTrue(all(
                        "/Top10/2025/" in item["reference_url"]
                        for item in checklist.json()
                    ))
                self.assertEqual(
                    self.client.delete(f"/api/engagements/{engagement_id}").status_code,
                    204,
                )

    def test_findings_csv_export_is_spreadsheet_safe_and_redacted_by_default(self):
        engagement = self.client.post(
            "/api/engagements",
            json={"name": "CSV Review", "client_name": "Local Test"},
        )
        self.assertEqual(engagement.status_code, 201, engagement.text)
        engagement_id = engagement.json()["id"]
        finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            json={
                "title": "=HYPERLINK(\"https://unsafe.example\")",
                "description": "Authorization: Bearer csv-secret-token",
                "severity": "high",
                "cvss_score": 0,
                "affected_hosts": "+example.test",
                "evidence": "Cookie: session=private-value",
                "remediation": "@apply policy",
            },
        )
        self.assertEqual(finding.status_code, 201, finding.text)

        redacted = self.client.get(f"/api/engagements/{engagement_id}/findings.csv")
        self.assertEqual(redacted.status_code, 200, redacted.text)
        self.assertIn("text/csv", redacted.headers["content-type"])
        self.assertIn("CSV-Review-findings-redacted.csv", redacted.headers["content-disposition"])
        rows = list(csv.DictReader(StringIO(redacted.text)))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["title"].startswith("'="))
        self.assertTrue(rows[0]["affected_hosts"].startswith("'+"))
        self.assertTrue(rows[0]["remediation"].startswith("'@"))
        self.assertEqual(rows[0]["cvss_score"], "0.0")
        self.assertNotIn("csv-secret-token", rows[0]["description"])
        self.assertNotIn("private-value", rows[0]["evidence"])
        self.assertIn("[REDACTED]", rows[0]["description"])

        raw = self.client.get(
            f"/api/engagements/{engagement_id}/findings.csv?redact_sensitive=false"
        )
        self.assertEqual(raw.status_code, 200, raw.text)
        raw_rows = list(csv.DictReader(StringIO(raw.text)))
        self.assertIn("csv-secret-token", raw_rows[0]["description"])
        self.assertNotIn("-redacted.csv", raw.headers["content-disposition"])
        self.assertEqual(
            self.client.delete(f"/api/engagements/{engagement_id}").status_code,
            204,
        )

    def test_ai_analysis_rejects_too_many_scans_before_provider_use(self):
        engagement = self.client.post(
            "/api/engagements",
            json={"name": "Bounded AI Input", "client_name": "Local Test"},
        )
        self.assertEqual(engagement.status_code, 201, engagement.text)
        engagement_id = engagement.json()["id"]
        for index in range(51):
            upload = self.client.post(
                f"/api/engagements/{engagement_id}/upload-scan?scan_type=custom",
                files={
                    "file": (
                        f"input-{index:02d}.txt",
                        b"bounded test evidence",
                        "text/plain",
                    )
                },
            )
            self.assertEqual(upload.status_code, 200, upload.text)
        analysis = self.client.post(
            f"/api/engagements/{engagement_id}/analyze"
        )
        self.assertEqual(analysis.status_code, 413, analysis.text)
        self.assertIn("at most 50 scan files", analysis.json()["detail"])
        preview = self.client.get(f"/api/engagements/{engagement_id}/analysis-preview")
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["scan_count"], 51)
        self.assertEqual(preview.json()["inspected_scan_count"], 50)
        self.assertFalse(preview.json()["total_bytes_complete"])
        self.assertFalse(preview.json()["ready"])
        self.assertIn("Remove 1 scan file", preview.json()["issues"][0])
        self.assertNotIn("api_key", preview.json())
        selected_preview = self.client.post(
            f"/api/engagements/{engagement_id}/analysis-preview",
            json={"scan_ids": [upload.json()["id"]]},
        )
        self.assertEqual(selected_preview.status_code, 200, selected_preview.text)
        self.assertEqual(selected_preview.json()["scan_count"], 1)
        self.assertTrue(selected_preview.json()["ready"])
        wrong_engagement_preview = self.client.post(
            f"/api/engagements/{engagement_id}/analysis-preview",
            json={"scan_ids": ["00000000-0000-0000-0000-000000000000"]},
        )
        self.assertEqual(wrong_engagement_preview.status_code, 422)
        self.assertEqual(
            self.client.delete(f"/api/engagements/{engagement_id}").status_code,
            204,
        )

    def test_diagnostics_detects_missing_database_backed_file(self):
        engagement = self.client.post(
            "/api/engagements",
            json={"name": "File Integrity", "client_name": "Local Test"},
        )
        self.assertEqual(engagement.status_code, 201, engagement.text)
        engagement_id = engagement.json()["id"]
        upload = self.client.post(
            f"/api/engagements/{engagement_id}/upload-scan?scan_type=custom",
            files={"file": ("integrity.txt", b"test evidence", "text/plain")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        stored_files = list((self.data_dir / "uploads" / engagement_id).iterdir())
        self.assertEqual(len(stored_files), 1)
        stored_files[0].unlink()
        diagnostics = self.client.get("/api/system/diagnostics")
        self.assertEqual(diagnostics.status_code, 200, diagnostics.text)
        self.assertEqual(diagnostics.json()["stored_files"]["status"], "missing_files")
        self.assertEqual(diagnostics.json()["stored_files"]["missing"], 1)
        self.assertEqual(
            self.client.delete(f"/api/engagements/{engagement_id}").status_code,
            204,
        )

    def test_scan_upload_auto_detection_uses_safe_fallback(self):
        engagement = self.client.post(
            "/api/engagements",
            json={"name": "Scan Detection", "client_name": "Local Test"},
        )
        self.assertEqual(engagement.status_code, 201, engagement.text)
        engagement_id = engagement.json()["id"]
        cases = [
            ("scan.xml", b"<?xml version='1.0'?><nmaprun></nmaprun>", "nmap"),
            ("audit.nessus", b"<NessusClientData_v2></NessusClientData_v2>", "nessus"),
            ("burp.xml", b"<items burpVersion='2026'><item></item></items>", "burp"),
            (
                "nuclei.jsonl",
                json.dumps({
                    "template-id": "test-template",
                    "matched-at": "https://example.test",
                    "info": {"name": "Test", "severity": "info"},
                }).encode("utf-8"),
                "nuclei",
            ),
            (
                "results.json",
                json.dumps({"version": "2.1.0", "runs": []}).encode("utf-8"),
                "sarif",
            ),
            ("notes.txt", b"unstructured analyst evidence", "custom"),
        ]
        for filename, content, expected_type in cases:
            upload = self.client.post(
                f"/api/engagements/{engagement_id}/upload-scan?scan_type=auto",
                files={"file": (filename, content, "application/octet-stream")},
            )
            self.assertEqual(upload.status_code, 200, upload.text)
            self.assertEqual(upload.json()["scan_type"], expected_type)
            self.assertTrue(upload.json()["auto_detected"])
            self.assertEqual(upload.json()["size_bytes"], len(content))
            self.assertTrue(upload.json()["stored_file_available"])
            self.assertIsNotNone(upload.json()["created_at"])
        manual_override = self.client.post(
            f"/api/engagements/{engagement_id}/upload-scan?scan_type=custom",
            files={
                "file": (
                    "nmap-looking.txt",
                    b"<nmaprun></nmaprun>",
                    "text/plain",
                )
            },
        )
        self.assertEqual(manual_override.json()["scan_type"], "custom")
        self.assertFalse(manual_override.json()["auto_detected"])
        self.assertEqual(
            self.client.delete(f"/api/engagements/{engagement_id}").status_code,
            204,
        )

    def test_engagement_evidence_notebook_notes_and_attachments(self):
        engagement = self.client.post(
            "/api/engagements",
            json={"name": "Evidence Notebook", "client_name": "Local Test"},
        )
        self.assertEqual(engagement.status_code, 201, engagement.text)
        engagement_id = engagement.json()["id"]

        invalid_tags = self.client.post(
            f"/api/engagements/{engagement_id}/notebook",
            json={"title": "Duplicate tags", "tags": ["HTTP", "http"]},
        )
        self.assertEqual(invalid_tags.status_code, 422, invalid_tags.text)

        created = self.client.post(
            f"/api/engagements/{engagement_id}/notebook",
            json={
                "title": "Administrative endpoint response",
                "body": "GET /admin HTTP/1.1\nHost: app.example.test",
                "asset": "app.example.test",
                "tags": ["http", "authorization"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        note_id = created.json()["id"]
        self.assertEqual(created.json()["attachments"], [])

        attachment = self.client.post(
            f"/api/engagements/{engagement_id}/notebook/{note_id}/attachments",
            files={
                "file": (
                    "../../admin-response.http",
                    b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n",
                    "application/octet-stream",
                )
            },
        )
        self.assertEqual(attachment.status_code, 200, attachment.text)
        attachment_id = attachment.json()["id"]
        self.assertEqual(attachment.json()["filename"], "admin-response.http")
        notebook_file = (
            self.data_dir / "notebook" / engagement_id / note_id
        )
        self.assertEqual(len(list(notebook_file.iterdir())), 1)

        listed = self.client.get(f"/api/engagements/{engagement_id}/notebook")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["total"], 1)
        self.assertFalse(listed.json()["truncated"])
        self.assertEqual(
            listed.json()["notes"][0]["attachments"][0]["id"],
            attachment_id,
        )
        note_search = self.client.get(
            f"/api/engagements/{engagement_id}/search?q=authorization"
        )
        self.assertEqual(note_search.status_code, 200, note_search.text)
        self.assertEqual(note_search.json()["results"][0]["type"], "notebook note")
        self.assertEqual(note_search.json()["results"][0]["tab"], "notebook")
        attachment_search = self.client.get(
            f"/api/engagements/{engagement_id}/search?q=admin-response"
        )
        self.assertEqual(attachment_search.status_code, 200, attachment_search.text)
        self.assertEqual(
            attachment_search.json()["results"][0]["type"],
            "notebook attachment",
        )

        downloaded = self.client.get(attachment.json()["url"])
        self.assertEqual(downloaded.status_code, 200, downloaded.text)
        self.assertEqual(downloaded.content, b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
        self.assertEqual(downloaded.headers["x-content-type-options"], "nosniff")
        self.assertIn("sandbox", downloaded.headers["content-security-policy"])

        updated = self.client.put(
            f"/api/engagements/{engagement_id}/notebook/{note_id}",
            json={
                "title": "Administrative endpoint access check",
                "body": "Anonymous request returned 403.",
                "asset": "app.example.test",
                "tags": ["http", "validated"],
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["attachments"][0]["id"], attachment_id)
        readiness_before_promotion = self.client.get(
            f"/api/engagements/{engagement_id}/report-readiness"
        )
        self.assertIn(
            "unreviewed_evidence_notes",
            {warning["code"] for warning in readiness_before_promotion.json()["warnings"]},
        )
        self.assertEqual(
            readiness_before_promotion.json()["summary"]["unreviewed_evidence_notes"],
            1,
        )

        promoted = self.client.post(
            f"/api/engagements/{engagement_id}/notebook/{note_id}/finding",
            json={
                "title": "Administrative endpoint behavior",
                "description": "The administrative endpoint was validated.",
                "severity": "medium",
                "affected_hosts": "app.example.test",
                "evidence": "Anonymous request returned 403.",
                "remediation": "Continue to enforce authorization on the endpoint.",
            },
        )
        self.assertEqual(promoted.status_code, 201, promoted.text)
        finding_id = promoted.json()["id"]
        self.assertEqual(promoted.json()["source"], "notebook_reviewed")
        self.assertFalse(promoted.json()["ai_inference"])
        evidence_ref = promoted.json()["evidence_refs"][0]
        self.assertEqual(evidence_ref["evidence_note_id"], note_id)
        self.assertEqual(evidence_ref["attachment_ids"], [attachment_id])
        self.assertEqual(evidence_ref["attachment_filenames"], ["admin-response.http"])
        history = self.client.get(
            f"/api/engagements/{engagement_id}/findings/{finding_id}/history"
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()[0]["action"], "notebook_note_accepted")
        self.assertEqual(history.json()[0]["source"], "notebook_reviewed")
        duplicate = self.client.post(
            f"/api/engagements/{engagement_id}/notebook/{note_id}/finding",
            json={"title": "Duplicate", "severity": "info"},
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        linked = self.client.get(f"/api/engagements/{engagement_id}/notebook")
        self.assertEqual(linked.json()["notes"][0]["finding_id"], finding_id)
        readiness_after_promotion = self.client.get(
            f"/api/engagements/{engagement_id}/report-readiness"
        )
        self.assertNotIn(
            "unreviewed_evidence_notes",
            {warning["code"] for warning in readiness_after_promotion.json()["warnings"]},
        )
        self.assertEqual(
            readiness_after_promotion.json()["summary"]["unreviewed_evidence_notes"],
            0,
        )
        locked_update = self.client.put(
            f"/api/engagements/{engagement_id}/notebook/{note_id}",
            json={"title": "Changed after promotion"},
        )
        self.assertEqual(locked_update.status_code, 409, locked_update.text)
        locked_attachment_delete = self.client.delete(
            f"/api/engagements/{engagement_id}/notebook/{note_id}/attachments/{attachment_id}"
        )
        self.assertEqual(locked_attachment_delete.status_code, 409, locked_attachment_delete.text)
        self.assertEqual(
            self.client.delete(f"/api/engagements/{engagement_id}/findings/{finding_id}").status_code,
            204,
        )

        self.assertEqual(
            self.client.delete(
                f"/api/engagements/{engagement_id}/notebook/{note_id}/attachments/{attachment_id}"
            ).status_code,
            204,
        )
        self.assertFalse(any(notebook_file.iterdir()))
        self.assertEqual(
            self.client.delete(
                f"/api/engagements/{engagement_id}/notebook/{note_id}"
            ).status_code,
            204,
        )
        self.assertFalse(notebook_file.exists())
        self.assertEqual(
            self.client.delete(f"/api/engagements/{engagement_id}").status_code,
            204,
        )

    def test_finding_template_crud_and_versioned_interchange(self):
        empty = self.client.get("/api/finding-templates")
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertEqual(empty.json(), [])

        rejected = self.client.post(
            "/api/finding-templates",
            json={
                "name": "Invalid score",
                "title": "Invalid",
                "severity": "high",
                "cvss_score": 10.1,
            },
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)

        created = self.client.post(
            "/api/finding-templates",
            json={
                "name": "SMB signing",
                "category": "Network",
                "title": "SMB signing is not required",
                "description": "The service permits unsigned SMB sessions.",
                "severity": "medium",
                "cvss_score": 5.3,
                "remediation": "Require SMB signing through policy.",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        template_id = created.json()["id"]
        self.assertEqual(created.json()["schema_version"], 1)

        updated = self.client.put(
            f"/api/finding-templates/{template_id}",
            json={
                "name": "SMB signing baseline",
                "category": "Windows",
                "title": "SMB signing is not required",
                "description": "The service permits unsigned SMB sessions.",
                "severity": "high",
                "cvss_score": 7.1,
                "remediation": "Require SMB signing through policy.",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["severity"], "high")

        exported = self.client.get(f"/api/finding-templates/{template_id}/export")
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertEqual(exported.json()["kind"], "breachwright-finding-template")
        self.assertEqual(exported.json()["version"], "1.0")
        self.assertNotIn("affected_hosts", exported.json()["template"])
        self.assertNotIn("evidence", exported.json()["template"])
        self.assertIn("attachment", exported.headers["content-disposition"])

        imported = self.client.post(
            "/api/finding-templates/import",
            files={
                "file": (
                    "smb.breachwright-finding.json",
                    exported.content,
                    "application/json",
                )
            },
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        imported_id = imported.json()["id"]
        self.assertNotEqual(imported_id, template_id)
        self.assertEqual(imported.json()["title"], updated.json()["title"])

        unsafe_document = exported.json()
        unsafe_document["template"]["affected_hosts"] = "target-specific.example"
        rejected_import = self.client.post(
            "/api/finding-templates/import",
            files={
                "file": (
                    "unsafe.json",
                    json.dumps(unsafe_document).encode("utf-8"),
                    "application/json",
                )
            },
        )
        self.assertEqual(rejected_import.status_code, 422, rejected_import.text)

        listed = self.client.get("/api/finding-templates")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()), 2)
        self.assertEqual(
            self.client.delete(f"/api/finding-templates/{template_id}").status_code,
            204,
        )
        self.assertEqual(
            self.client.delete(f"/api/finding-templates/{imported_id}").status_code,
            204,
        )
        self.assertEqual(
            self.client.get(f"/api/finding-templates/{template_id}/export").status_code,
            404,
        )

    def test_custom_assessment_template_crud_interchange_and_engagement_creation(self):
        templates = self.client.get("/api/assessment-templates")
        self.assertEqual(templates.status_code, 200, templates.text)
        self.assertEqual(len([item for item in templates.json() if item["built_in"]]), 6)
        methodologies = self.client.get("/api/assessment-templates/methodologies")
        self.assertEqual(methodologies.status_code, 200, methodologies.text)
        self.assertIn("network_pentest", methodologies.json())
        duplicate_methodologies = self.client.post(
            "/api/assessment-templates",
            json={"name": "Invalid duplicate", "methodologies": ["ptes", "ptes"]},
        )
        self.assertEqual(duplicate_methodologies.status_code, 422)
        created = self.client.post(
            "/api/assessment-templates",
            json={
                "name": "Internal and API Review",
                "description": "Reusable combined assessment start.",
                "methodologies": ["network_pentest", "owasp_api_top10"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        template_key = created.json()["key"]
        self.assertTrue(template_key.startswith("user-"))
        self.assertFalse(created.json()["built_in"])
        updated = self.client.put(
            f"/api/assessment-templates/{template_key}",
            json={
                "name": "Internal and API Assessment",
                "description": "Updated reusable start.",
                "methodologies": ["network_pentest", "owasp_api_top10"],
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["name"], "Internal and API Assessment")
        self.assertEqual(self.client.delete("/api/assessment-templates/web").status_code, 409)
        unknown_template = self.client.post(
            "/api/engagements",
            json={"name": "Unknown template", "client_name": "Local Test", "template_key": "user-missing"},
        )
        self.assertEqual(unknown_template.status_code, 422, unknown_template.text)
        engagement = self.client.post(
            "/api/engagements",
            json={"name": "Custom Template Engagement", "client_name": "Local Test", "template_key": template_key},
        )
        self.assertEqual(engagement.status_code, 201, engagement.text)
        checklist = self.client.get(f"/api/engagements/{engagement.json()['id']}/checklists")
        self.assertEqual(
            {item["methodology"] for item in checklist.json()},
            {"network_pentest", "owasp_api_top10"},
        )
        exported = self.client.get(f"/api/assessment-templates/{template_key}/export")
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertEqual(exported.json()["version"], "1.0")
        self.assertIn("attachment", exported.headers["content-disposition"])
        imported = self.client.post(
            "/api/assessment-templates/import",
            files={"file": ("combined.breachwright-template.json", exported.content, "application/json")},
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertNotEqual(imported.json()["key"], template_key)
        self.assertEqual(imported.json()["methodologies"], created.json()["methodologies"])
        self.assertEqual(self.client.delete(f"/api/assessment-templates/{template_key}").status_code, 204)
        checklist_after_delete = self.client.get(f"/api/engagements/{engagement.json()['id']}/checklists")
        self.assertEqual(len(checklist_after_delete.json()), len(checklist.json()))
        self.assertEqual(self.client.delete(f"/api/assessment-templates/{imported.json()['key']}").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/engagements/{engagement.json()['id']}").status_code, 204)


if __name__ == "__main__":
    unittest.main()
