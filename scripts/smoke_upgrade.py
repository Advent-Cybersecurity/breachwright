"""Verify that a v2.0.0 data directory upgrades cleanly to the candidate."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import httpx


CURRENT_ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def start_application(
    root: Path,
    environment: dict[str, str],
) -> tuple[subprocess.Popen, httpx.Client]:
    port = free_port()
    log_path = Path(environment["UPGRADE_SMOKE_ROOT"]) / (
        f"{root.name}-{port}.log"
    )
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(root / "backend"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=root,
        env={
            **environment,
            "PYTHONPATH": str(root / "backend"),
            "PYTHONUNBUFFERED": "1",
        },
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        timeout=20,
    )
    deadline = time.monotonic() + 40
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                response = client.get("/api/health", timeout=2)
                if response.status_code == 200:
                    process._breachwright_log_file = log_file
                    return process, client
            except httpx.HTTPError:
                time.sleep(0.2)
        log_file.flush()
        logs = log_path.read_text(encoding="utf-8", errors="replace")
        raise RuntimeError(f"Application did not become healthy:\n{logs}")
    except Exception:
        client.close()
        stop_process_tree(process)
        log_file.close()
        raise


def stop_application(process: subprocess.Popen, client: httpx.Client) -> None:
    client.close()
    stop_process_tree(process)
    log_file = getattr(process, "_breachwright_log_file", None)
    if log_file:
        log_file.close()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: smoke_upgrade.py <v2.0.0 source directory>")
    baseline_root = Path(sys.argv[1]).resolve()
    if not (baseline_root / "backend" / "app" / "main.py").is_file():
        raise SystemExit(f"Invalid v2.0.0 source directory: {baseline_root}")

    temp_root = (
        Path(tempfile.gettempdir())
        / f"breachwright-upgrade-smoke-{uuid.uuid4().hex}"
    )
    temp_root.mkdir()
    data_dir = temp_root / "data"
    database_path = data_dir / "breachwright.db"
    environment = os.environ.copy()
    environment.update(
        {
            "UPGRADE_SMOKE_ROOT": str(temp_root),
            "APPDATA": str(temp_root / "appdata"),
            "XDG_DATA_HOME": str(temp_root / "xdg"),
            "DATA_DIR": str(data_dir),
            "DATABASE_URL": (
                "sqlite+aiosqlite:///" + database_path.as_posix()
            ),
            "SECRET_KEY": "upgrade-smoke-only-secret",
            "DESKTOP": "false",
        }
    )

    email = "upgrade@example.com"
    password = "upgrade-smoke-password"
    engagement_id = None
    try:
        baseline_process, baseline_client = start_application(
            baseline_root,
            environment,
        )
        try:
            setup = baseline_client.post(
                "/api/auth/setup",
                json={
                    "email": email,
                    "password": password,
                    "display_name": "Upgrade Smoke",
                },
            )
            setup.raise_for_status()
            login = baseline_client.post(
                "/api/auth/login",
                json={"email": email, "password": password},
            )
            login.raise_for_status()
            headers = {
                "Authorization": f"Bearer {login.json()['access_token']}"
            }
            engagement = baseline_client.post(
                "/api/engagements",
                headers=headers,
                json={
                    "name": "v2.0 Upgrade Assessment",
                    "client_name": "Upgrade Client",
                    "scope": "upgrade.example",
                },
            )
            engagement.raise_for_status()
            engagement_id = engagement.json()["id"]
            finding = baseline_client.post(
                f"/api/engagements/{engagement_id}/findings",
                headers=headers,
                json={
                    "title": "Legacy finding survives",
                    "severity": "high",
                    "description": "Created by the v2.0.0 application.",
                },
            )
            finding.raise_for_status()
        finally:
            stop_application(baseline_process, baseline_client)

        candidate_process, candidate_client = start_application(
            CURRENT_ROOT,
            environment,
        )
        try:
            health = candidate_client.get("/api/health")
            health.raise_for_status()
            if health.json().get("version") != "2.1.0-rc.1":
                raise RuntimeError("Candidate version was not loaded")
            login = candidate_client.post(
                "/api/auth/login",
                json={"email": email, "password": password},
            )
            login.raise_for_status()
            headers = {
                "Authorization": f"Bearer {login.json()['access_token']}"
            }
            engagement = candidate_client.get(
                f"/api/engagements/{engagement_id}",
                headers=headers,
            )
            engagement.raise_for_status()
            if engagement.json()["name"] != "v2.0 Upgrade Assessment":
                raise RuntimeError("Legacy engagement data changed")
            findings = candidate_client.get(
                f"/api/engagements/{engagement_id}/findings",
                headers=headers,
            )
            findings.raise_for_status()
            if [item["title"] for item in findings.json()] != [
                "Legacy finding survives"
            ]:
                raise RuntimeError("Legacy finding data changed")
            report = candidate_client.post(
                f"/api/engagements/{engagement_id}/reports",
                headers=headers,
                params={"format": "md", "use_ai": "false"},
            )
            report.raise_for_status()
        finally:
            stop_application(candidate_process, candidate_client)

        print("v2.0.0 to v2.1.0-rc.1 upgrade smoke test passed")
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
