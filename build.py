#!/usr/bin/env python3
"""Reproducible cross-platform Breachwright candidate builder."""

from __future__ import annotations

import argparse
from importlib import metadata
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SPEC_FILE = PROJECT_ROOT / "breachwright.spec"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
MINIMUM_NODE_MAJOR = 20

sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from app.version import APP_VERSION


def run(command: list[str], cwd: Path = PROJECT_ROOT) -> None:
    print(f"> {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def validate_node_version(node: str) -> None:
    try:
        result = subprocess.run(
            [node, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("Unable to determine the installed Node.js version.") from exc
    match = re.fullmatch(r"v?(\d+)(?:\.\d+){1,2}", result.stdout.strip())
    if not match:
        raise SystemExit("Unable to determine the installed Node.js version.")
    if int(match.group(1)) < MINIMUM_NODE_MAJOR:
        raise SystemExit(
            f"Node.js {MINIMUM_NODE_MAJOR} or newer is required "
            f"(found {result.stdout.strip()})."
        )


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
        validate_node_version(shutil.which("node") or "node")


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
        "SECURITY.md",
        "SUPPORT.md",
        "CHANGELOG.md",
        "ROADMAP.md",
        "INSTALL.md",
        "INSTALL_WSL.md",
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
    if sys.platform == "win32":
        runtime_config = (
            PROJECT_ROOT / "packaging" / "windows" / "Breachwright.exe.config"
        )
        if not runtime_config.is_file():
            raise SystemExit(
                f"Windows runtime configuration is missing: {runtime_config}"
            )
        for executable_name in ("Breachwright.exe", "BreachwrightCLI.exe"):
            shutil.copy2(runtime_config, bundle_dir / f"{executable_name}.config")
    bundled_docs = bundle_dir / "docs"
    for document_name in (
        "DATA_SAFETY.md",
        f"RELEASE_NOTES_{APP_VERSION}.md",
    ):
        source = PROJECT_ROOT / "docs" / document_name
        if source.is_file():
            bundled_docs.mkdir(exist_ok=True)
            shutil.copy2(source, bundled_docs / document_name)
    (bundle_dir / "VERSION").write_text(f"{APP_VERSION}\n", encoding="utf-8")


def _safe_path_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-") or "unknown"


def _is_license_file(path: Path) -> bool:
    return path.name.lower().startswith(
        ("license", "licence", "copying", "notice", "authors", "copyright")
    )


def _node_package_roots(node_modules: Path):
    """Yield installed npm package roots, including nested dependencies."""
    pending = [node_modules]
    visited: set[Path] = set()
    while pending:
        modules = pending.pop()
        try:
            resolved = modules.resolve()
        except OSError:
            continue
        if resolved in visited or not modules.is_dir():
            continue
        visited.add(resolved)
        for entry in modules.iterdir():
            if entry.name.startswith("."):
                continue
            package_dirs = (
                list(entry.iterdir())
                if entry.name.startswith("@") and entry.is_dir()
                else [entry]
            )
            for package_dir in package_dirs:
                if not (package_dir / "package.json").is_file():
                    continue
                yield package_dir
                nested = package_dir / "node_modules"
                if nested.is_dir():
                    pending.append(nested)


def include_dependency_licenses(bundle_dir: Path) -> None:
    """Bundle license texts exposed by installed Python and npm packages."""
    license_root = bundle_dir / "THIRD_PARTY_LICENSES"
    python_root = license_root / "python"
    javascript_root = license_root / "javascript"
    copied_paths: set[Path] = set()

    for distribution in metadata.distributions():
        distribution_name = distribution.metadata.get("Name") or "unknown"
        destination_name = _safe_path_component(
            f"{distribution_name}-{distribution.version}"
        )
        for item in distribution.files or ():
            parts = list(item.parts)
            dist_info_index = next(
                (
                    index
                    for index, part in enumerate(parts)
                    if part.lower().endswith(".dist-info")
                ),
                None,
            )
            if dist_info_index is None:
                continue
            relative = Path(*parts[dist_info_index + 1 :])
            if (
                not relative.parts
                or relative.is_absolute()
                or ".." in relative.parts
            ):
                continue
            if not (
                _is_license_file(relative)
                or "licenses" in {part.lower() for part in relative.parts}
            ):
                continue
            source = Path(distribution.locate_file(item))
            if not source.is_file():
                continue
            destination = python_root / destination_name / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied_paths.add(destination)

    node_modules = FRONTEND_DIR / "node_modules"
    if node_modules.is_dir():
        for package_dir in _node_package_roots(node_modules):
            try:
                package = json.loads(
                    (package_dir / "package.json").read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            destination_name = _safe_path_component(
                f"{package.get('name', package_dir.name)}-"
                f"{package.get('version', 'unknown')}"
            )
            for source in package_dir.iterdir():
                if not source.is_file() or not _is_license_file(source):
                    continue
                destination = javascript_root / destination_name / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied_paths.add(destination)

    if not copied_paths:
        raise SystemExit("No dependency license files were found for the bundle.")
    license_root.mkdir(parents=True, exist_ok=True)
    (license_root / "README.txt").write_text(
        "License texts collected from installed dependency metadata at build "
        "time. See ../THIRD_PARTY_NOTICES.md for the dependency summary.\n",
        encoding="utf-8",
    )
    print(f"Bundled {len(copied_paths)} dependency license files.")


def validate_bundle(executable: Path, run_executable: bool) -> None:
    internal = executable.parent / "_internal"
    required = [
        internal / "frontend" / "dist" / "index.html",
        internal / "backend" / "alembic.ini",
        internal / "backend" / "alembic" / "versions",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if sys.platform == "win32":
        missing.extend(
            str(executable.parent / name)
            for name in (
                "Breachwright.exe.config",
                "BreachwrightCLI.exe.config",
            )
            if not (executable.parent / name).is_file()
        )
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
    include_dependency_licenses(executable.parent)
    validate_bundle(executable, not args.skip_executable_smoke)
    archive = package_bundle()
    print(f"Candidate bundle: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
