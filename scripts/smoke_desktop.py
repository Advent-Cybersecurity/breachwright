"""Verify that a packaged Breachwright desktop window stays healthy."""

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
        process.wait(timeout=10)
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: smoke_desktop.py <Breachwright executable>")
    executable = Path(sys.argv[1]).resolve()
    if not executable.is_file():
        raise SystemExit(f"Executable not found: {executable}")

    port = free_port()
    with tempfile.TemporaryDirectory(prefix="breachwright-desktop-smoke-") as temp_dir:
        ready_file = Path(temp_dir) / "desktop-ready"
        env = os.environ.copy()
        env.update(
            {
                "DATA_DIR": str(Path(temp_dir) / "data"),
                "DESKTOP": "true",
                "BREACHWRIGHT_DESKTOP_READY_FILE": str(ready_file),
            }
        )
        process = subprocess.Popen(
            [str(executable), "--host", "127.0.0.1", "--port", str(port)],
            env=env,
        )
        try:
            deadline = time.monotonic() + 45
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}",
                timeout=2,
            ) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(
                            f"Desktop process exited with code {process.returncode}"
                        )
                    try:
                        health = client.get("/api/health").json()
                        if health.get("status") == "healthy" and ready_file.is_file():
                            time.sleep(3)
                            if process.poll() is not None:
                                raise RuntimeError(
                                    "Desktop process exited after becoming healthy"
                                )
                            print(
                                "Desktop smoke test passed: "
                                f"{health.get('version')} on {sys.platform}"
                            )
                            return 0
                    except (httpx.HTTPError, ValueError):
                        time.sleep(0.2)
            raise RuntimeError(
                "Desktop application did not become healthy and show its window"
            )
        finally:
            stop_process_tree(process)


if __name__ == "__main__":
    raise SystemExit(main())
