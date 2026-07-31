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
            400,
            invalid_checklist_status.text,
        )
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
        self.assertEqual(exported_finding["evidence_refs"][0]["id"], "CF-0001-E01")

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

        finding = self.client.post(
            f"/api/engagements/{engagement_id}/findings",
            json={
                "title": "Administrative endpoint exposed",
                "severity": "high",
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

        readiness = self.client.get(f"/api/engagements/{engagement_id}/report-readiness")
        self.assertEqual(readiness.status_code, 200, readiness.text)
        self.assertFalse(readiness.json()["ready"])
        self.assertEqual(len(readiness.json()["blockers"]), 2)
        updated = self.client.put(
            f"/api/engagements/{engagement_id}/findings/{finding_id}",
            json={
                "evidence": "The endpoint returned an administrative console.",
                "remediation": "Require authorization for the administrative route.",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        history = self.client.get(
            f"/api/engagements/{engagement_id}/findings/{finding_id}/history"
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual([entry["action"] for entry in history.json()], ["updated", "created"])
        self.assertIn("evidence", history.json()[0]["changes"])
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
        snapshot3 = self.client.post(
            f"/api/engagements/{engagement_id}/scan-snapshots",
            json={"label": "Retest 2", "scan_ids": [scan_a2]},
        )
        self.assertEqual(snapshot3.status_code, 201, snapshot3.text)
        self.assertEqual(snapshot3.json()["counts"], {"new": 0, "persistent": 1, "resolved": 0, "regressed": 1})
        replay = self.client.get(
            f"/api/engagements/{engagement_id}/scan-snapshots/{snapshot3.json()['snapshot']['id']}/comparison"
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["counts"], snapshot3.json()["counts"])

        sarif = self.client.get(f"/api/engagements/{engagement_id}/findings.sarif")
        self.assertEqual(sarif.status_code, 200, sarif.text)
        self.assertEqual(sarif.json()["version"], "2.1.0")
        self.assertEqual(len(sarif.json()["runs"][0]["results"]), 1)
        self.assertIn("attachment", sarif.headers["content-disposition"])
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

        portable = self.client.get(f"/api/engagements/{engagement_id}/export")
        self.assertEqual(portable.status_code, 200, portable.text)
        self.assertEqual(portable.json()["version"], "1.1")
        self.assertEqual(portable.json()["engagement"]["template_key"], "web")
        self.assertEqual(portable.json()["findings"][0]["retest_due_date"], "2020-01-02")
        imported = self.client.post(
            "/api/engagements/import",
            files={"file": ("repeatable-export.json", portable.content, "application/json")},
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        imported_id = imported.json()["id"]
        imported_engagement = self.client.get(f"/api/engagements/{imported_id}")
        self.assertEqual(imported_engagement.json()["template_key"], "web")
        imported_findings = self.client.get(f"/api/engagements/{imported_id}/findings")
        self.assertEqual(imported_findings.json()[0]["retest_due_date"], "2020-01-02")
        imported_history = self.client.get(
            f"/api/engagements/{imported_id}/findings/{imported_findings.json()[0]['id']}/history"
        )
        self.assertEqual(imported_history.json()[0]["action"], "imported")
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


if __name__ == "__main__":
    unittest.main()
