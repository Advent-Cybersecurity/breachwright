"""Launch a packaged Breachwright executable and verify its web application."""

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
                },
            )
            engagement.raise_for_status()
            engagement_id = engagement.json()["id"]
            finding = client.post(
                f"/api/engagements/{engagement_id}/findings",
                headers=headers,
                json={
                    "title": "Packaged finding",
                    "severity": "medium",
                    "description": "Created by the packaged smoke test.",
                    "remediation": "Verify the candidate workflow.",
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
