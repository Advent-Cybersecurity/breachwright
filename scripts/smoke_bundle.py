"""Launch a packaged Breachwright executable and verify its web application."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: smoke_bundle.py <Breachwright executable>")
    executable = Path(sys.argv[1]).resolve()
    if not executable.is_file():
        raise SystemExit(f"Executable not found: {executable}")

    port = free_port()
    with tempfile.TemporaryDirectory(prefix="breachwright-bundle-smoke-") as temp_dir:
        env = os.environ.copy()
        env.update(
            {
                "DATA_DIR": str(Path(temp_dir) / "data"),
                "DESKTOP": "false",
            }
        )
        process = subprocess.Popen(
            [
                str(executable),
                "--headless",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=env,
        )
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=20)
        try:
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Packaged application exited with code {process.returncode}"
                    )
                try:
                    health = client.get("/api/health", timeout=2).json()
                    if (
                        health.get("status") == "healthy"
                        and health.get("distribution") == "open_source"
                    ):
                        index = client.get("/").content
                        if b'<div id="root">' not in index:
                            raise RuntimeError("Packaged frontend root was not served")
                        break
                except (httpx.HTTPError, ValueError):
                    time.sleep(0.2)
            else:
                raise RuntimeError("Packaged application did not become healthy")

            if client.get("/api/engagements").status_code != 200:
                raise RuntimeError("Packaged local workspace was not immediately usable")
            if client.get("/api/auth/login").status_code != 404:
                raise RuntimeError("Packaged authentication routes are still exposed")
            headers = {}
            engagement = client.post(
                "/api/engagements",
                headers=headers,
                json={
                    "name": "Packaged Smoke Assessment",
                    "client_name": "Example Client",
                    "scope": "example.test",
                    "template_key": "web",
                },
            )
            engagement.raise_for_status()
            engagement_id = engagement.json()["id"]
            if engagement.json().get("template_key") != "web":
                raise RuntimeError("Packaged engagement template was not retained")
            checklist = client.get(f"/api/engagements/{engagement_id}/checklists")
            checklist.raise_for_status()
            if not checklist.json() or any(
                item.get("methodology") != "owasp_top10"
                for item in checklist.json()
            ):
                raise RuntimeError("Packaged web template did not create its checklist")
            finding = client.post(
                f"/api/engagements/{engagement_id}/findings",
                headers=headers,
                json={
                    "title": "Packaged finding",
                    "severity": "high",
                    "description": "Created by the packaged smoke test.",
                    "affected_hosts": "https://example.test/admin",
                    "remediation": "Verify the candidate workflow.",
                    "retest_status": "retest_needed",
                    "retest_due_date": "2099-01-02",
                },
            )
            finding.raise_for_status()
            finding_id = finding.json()["id"]
            evidence = client.post(
                f"/api/engagements/{engagement_id}/findings/{finding_id}/evidence",
                headers=headers,
                files={"file": ("proof.png", b"\x89PNG\r\n\x1a\nsmoke", "image/png")},
            )
            evidence.raise_for_status()
            updated = client.put(
                f"/api/engagements/{engagement_id}/findings/{finding_id}",
                headers=headers,
                json={"evidence": "The administrative endpoint was reachable."},
            )
            updated.raise_for_status()
            history = client.get(
                f"/api/engagements/{engagement_id}/findings/{finding_id}/history",
                headers=headers,
            )
            history.raise_for_status()
            if [entry.get("action") for entry in history.json()] != [
                "updated",
                "created",
            ]:
                raise RuntimeError("Packaged finding history was incomplete")
            queue = client.get(
                f"/api/engagements/{engagement_id}/retest-queue",
                headers=headers,
            )
            queue.raise_for_status()
            if not queue.json() or queue.json()[0].get("id") != finding_id:
                raise RuntimeError("Packaged retest queue did not include the finding")
            readiness = client.get(
                f"/api/engagements/{engagement_id}/report-readiness",
                headers=headers,
            )
            readiness.raise_for_status()
            if not readiness.json().get("ready"):
                raise RuntimeError(
                    f"Packaged report readiness had blockers: {readiness.json().get('blockers')}"
                )

            nuclei_record = json.dumps(
                {
                    "template-id": "exposed-admin-panel",
                    "host": "example.test",
                    "matched-at": "https://example.test/admin",
                    "info": {
                        "name": "Exposed Admin Panel",
                        "severity": "high",
                    },
                }
            )
            upload = client.post(
                f"/api/engagements/{engagement_id}/upload-scan?scan_type=nuclei",
                headers=headers,
                files={
                    "file": (
                        "packaged-nuclei.jsonl",
                        nuclei_record.encode("utf-8"),
                        "application/x-ndjson",
                    )
                },
            )
            upload.raise_for_status()
            snapshot = client.post(
                f"/api/engagements/{engagement_id}/scan-snapshots",
                headers=headers,
                json={"label": "Packaged baseline", "scan_ids": [upload.json()["id"]]},
            )
            snapshot.raise_for_status()
            if snapshot.json().get("counts") != {
                "new": 1,
                "persistent": 0,
                "resolved": 0,
                "regressed": 0,
            }:
                raise RuntimeError(
                    f"Packaged snapshot comparison was unexpected: {snapshot.json().get('counts')}"
                )
            if snapshot.json().get("snapshot", {}).get("parser_version") != "structured-v1":
                raise RuntimeError("Packaged snapshot parser version was not recorded")

            sarif = client.get(
                f"/api/engagements/{engagement_id}/findings.sarif",
                headers=headers,
            )
            sarif.raise_for_status()
            if (
                sarif.json().get("version") != "2.1.0"
                or len(sarif.json().get("runs", [{}])[0].get("results", [])) != 1
            ):
                raise RuntimeError("Packaged SARIF export was invalid")
            sarif_upload = client.post(
                f"/api/engagements/{engagement_id}/upload-scan?scan_type=sarif",
                headers=headers,
                files={
                    "file": (
                        "packaged-findings.sarif",
                        sarif.content,
                        "application/sarif+json",
                    )
                },
            )
            sarif_upload.raise_for_status()
            report = client.post(
                f"/api/engagements/{engagement_id}/reports",
                headers=headers,
                params={"format": "docx"},
            )
            report.raise_for_status()
            report_file = client.get(
                f"/api/reports/{report.json()['id']}/download",
                headers=headers,
            )
            report_file.raise_for_status()
            if not report_file.content.startswith(b"PK"):
                raise RuntimeError("Packaged DOCX report was not a valid ZIP container")
        finally:
            client.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        cli_name = (
            "BreachwrightCLI.exe"
            if sys.platform == "win32"
            else "BreachwrightCLI"
        )
        cli = executable.with_name(cli_name)
        if not cli.is_file():
            raise RuntimeError(f"Packaged CLI not found: {cli}")
        version = subprocess.run(
            [str(cli), "--version"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        if version != f"Breachwright {health.get('version')}":
            raise RuntimeError(f"Packaged CLI reported an unexpected version: {version}")
        bedrock_env = env.copy()
        bedrock_env.update(
            {
                "AI_PROVIDER": "bedrock",
                "AWS_ACCESS_KEY_ID": "packaging-test",
                "AWS_SECRET_ACCESS_KEY": "packaging-test",
                "AWS_EC2_METADATA_DISABLED": "true",
            }
        )
        provider_status = subprocess.run(
            [str(cli), "--provider-status"],
            env=bedrock_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        if not provider_status.startswith("AI provider ready: Bedrock ("):
            raise RuntimeError(
                f"Packaged Bedrock provider was unavailable: {provider_status}"
            )
        subprocess.run(
            [str(cli), "--create-backup"],
            env=env,
            check=True,
            timeout=60,
        )
        backups = sorted(
            (Path(temp_dir) / "data" / "backups").glob(
                "breachwright-backup-*.zip"
            )
        )
        if len(backups) != 1:
            raise RuntimeError("Packaged CLI did not create exactly one backup")
        subprocess.run(
            [
                str(cli),
                "--restore-backup",
                str(backups[0]),
                "--confirm-restore",
            ],
            env=env,
            check=True,
            timeout=60,
        )
        print(
            "Packaged end-to-end smoke test passed: "
            f"{health.get('version')} on {sys.platform}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
