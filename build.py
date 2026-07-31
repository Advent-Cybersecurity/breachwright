#!/usr/bin/env python3
"""Reproducible cross-platform Breachwright candidate builder."""

from __future__ import annotations

import argparse
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SPEC_FILE = PROJECT_ROOT / "breachwright.spec"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"

sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from app.version import APP_VERSION


def run(command: list[str], cwd: Path = PROJECT_ROOT) -> None:
    print(f"> {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def validate_tools(skip_frontend: bool) -> None:
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required.")
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller is required. Install backend/requirements-build.txt."
        ) from exc
    if not skip_frontend:
        for executable in ("node", "npm"):
            if not shutil.which(executable):
                raise SystemExit(f"{executable} is required to build the frontend.")


def clean() -> None:
    for path in (BUILD_DIR, DIST_DIR):
        if path.exists():
            shutil.rmtree(path)


def build_frontend(skip_frontend: bool) -> None:
    if skip_frontend:
        if not (FRONTEND_DIR / "dist" / "index.html").is_file():
            raise SystemExit(
                "--skip-frontend requires frontend/dist/index.html to exist."
            )
        return
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        raise SystemExit("npm is required to build the frontend.")
    if sys.platform == "win32":
        command_prefix = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/s",
            "/c",
            npm,
        ]
    else:
        command_prefix = [npm]
    run([*command_prefix, "ci"], cwd=FRONTEND_DIR)
    run([*command_prefix, "run", "build"], cwd=FRONTEND_DIR)
    if not (FRONTEND_DIR / "dist" / "index.html").is_file():
        raise SystemExit("Frontend build did not produce index.html.")


def build_bundle() -> Path:
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC_FILE),
        ]
    )
    executable_name = "Breachwright.exe" if sys.platform == "win32" else "Breachwright"
    executable = DIST_DIR / "Breachwright" / executable_name
    if not executable.is_file():
        raise SystemExit(f"Expected executable was not created: {executable}")
    cli_name = "BreachwrightCLI.exe" if sys.platform == "win32" else "BreachwrightCLI"
    cli_executable = DIST_DIR / "Breachwright" / cli_name
    if not cli_executable.is_file():
        raise SystemExit(f"Expected CLI executable was not created: {cli_executable}")
    return executable


def include_distribution_files(bundle_dir: Path) -> None:
    names = [
        "README.md",
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
        "TRADEMARKS.md",
        "CHANGELOG.md",
        "icon.ico",
        "icon.png",
    ]
    names.extend(
        ["install-windows.bat", "uninstall-windows.bat"]
        if sys.platform == "win32"
        else ["install.sh", "uninstall.sh"]
    )
    for name in names:
        source = PROJECT_ROOT / name
        if source.is_file():
            shutil.copy2(source, bundle_dir / name)
    (bundle_dir / "VERSION").write_text(f"{APP_VERSION}\n", encoding="utf-8")


def validate_bundle(executable: Path, run_executable: bool) -> None:
    internal = executable.parent / "_internal"
    required = [
        internal / "frontend" / "dist" / "index.html",
        internal / "backend" / "alembic.ini",
        internal / "backend" / "alembic" / "versions",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Bundle is missing required files:\n" + "\n".join(missing))
    if run_executable:
        run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "smoke_bundle.py"),
                str(executable),
            ]
        )


def package_bundle() -> Path:
    system_name = "windows" if sys.platform == "win32" else "linux"
    machine = platform.machine().lower()
    architecture = "x64" if machine in {"amd64", "x86_64"} else machine
    base_name = DIST_DIR / f"breachwright-{APP_VERSION}-{system_name}-{architecture}"
    archive_format = "zip" if sys.platform == "win32" else "gztar"
    archive = shutil.make_archive(
        str(base_name),
        archive_format,
        root_dir=DIST_DIR,
        base_dir="Breachwright",
    )
    return Path(archive)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Reuse an existing frontend/dist build.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing build and dist directories first.",
    )
    parser.add_argument(
        "--skip-executable-smoke",
        action="store_true",
        help="Validate files but do not launch the built executable.",
    )
    args = parser.parse_args()

    validate_tools(args.skip_frontend)
    if args.clean:
        clean()
    build_frontend(args.skip_frontend)
    executable = build_bundle()
    include_distribution_files(executable.parent)
    validate_bundle(executable, not args.skip_executable_smoke)
    archive = package_bundle()
    print(f"Candidate bundle: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
