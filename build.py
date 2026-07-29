#!/usr/bin/env python3
"""
Breachwright — Build Script
============================
Orchestrates the full build pipeline:

    1. Validate prerequisites (Node, npm, Python deps, PyInstaller)
    2. Build the Vite frontend  → frontend/dist/
    3. Run PyInstaller           → dist/Breachwright/
    4. Smoke-test the output

Usage:
    python build.py                   # Full build
    python build.py --skip-frontend   # Skip npm build (reuse existing dist/)
    python build.py --onefile         # Produce a single executable
    python build.py --clean           # Wipe build artifacts first
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
SPEC_FILE    = PROJECT_ROOT / "breachwright.spec"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR     = PROJECT_ROOT / "dist"
BUILD_DIR    = PROJECT_ROOT / "build"

# ANSI colours (disabled on Windows without colorama)
_NO_COLOR = os.environ.get("NO_COLOR") or (sys.platform == "win32" and not os.environ.get("ANSICON"))
GREEN  = "" if _NO_COLOR else "\033[92m"
YELLOW = "" if _NO_COLOR else "\033[93m"
RED    = "" if _NO_COLOR else "\033[91m"
RESET  = "" if _NO_COLOR else "\033[0m"
BOLD   = "" if _NO_COLOR else "\033[1m"


def info(msg: str)  -> None: print(f"{GREEN}✓{RESET} {msg}")
def warn(msg: str)  -> None: print(f"{YELLOW}⚠{RESET} {msg}")
def error(msg: str) -> None: print(f"{RED}✗{RESET} {msg}")
def header(msg: str)-> None: print(f"\n{BOLD}{'═'*60}\n  {msg}\n{'═'*60}{RESET}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run(cmd: list[str] | str, cwd: Path | None = None, check: bool = True, **kw):
    """Run a subprocess, echoing the command."""
    if isinstance(cmd, str):
        cmd_str = cmd
    else:
        cmd_str = " ".join(str(c) for c in cmd)
    print(f"  $ {cmd_str}")
    return subprocess.run(cmd, cwd=cwd, check=check, **kw)


def which(binary: str) -> str | None:
    return shutil.which(binary)


def check_python_package(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def step_validate():
    """Ensure all build tools are available."""
    header("Step 1/4 — Validating prerequisites")

    ok = True

    # Python version
    py_ver = sys.version_info
    info(f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver < (3, 10):
        error("Python 3.10+ required")
        ok = False

    # PyInstaller
    if check_python_package("PyInstaller"):
        import PyInstaller
        info(f"PyInstaller {PyInstaller.__version__}")
    else:
        error("PyInstaller not installed — pip install pyinstaller")
        ok = False

    # Node / npm (for frontend build)
    node = which("node")
    if node:
        ver = subprocess.check_output(["node", "--version"], text=True).strip()
        info(f"Node.js {ver}")
    else:
        warn("Node.js not found — frontend build will be skipped")

    npm = which("npm")
    if npm:
        ver = subprocess.check_output(["npm", "--version"], text=True).strip()
        info(f"npm {ver}")
    else:
        warn("npm not found")

    # Key Python deps
    for pkg_import, pkg_label in [
        ("fastapi",  "FastAPI"),
        ("uvicorn",  "Uvicorn"),
        ("webview",  "pywebview"),
        ("sqlalchemy", "SQLAlchemy"),
        ("alembic",  "Alembic"),
        ("docx",     "python-docx"),
    ]:
        if check_python_package(pkg_import):
            info(f"{pkg_label} found")
        else:
            error(f"{pkg_label} not installed (import {pkg_import} failed)")
            ok = False

    if not ok:
        error("Fix the issues above and re-run.")
        sys.exit(1)


def step_build_frontend(skip: bool = False):
    header("Step 2/4 — Building frontend")

    if skip:
        warn("--skip-frontend: reusing existing frontend/dist/")
        if not (FRONTEND_DIR / "dist" / "index.html").exists():
            error("frontend/dist/index.html not found. Run without --skip-frontend.")
            sys.exit(1)
        return

    if not (FRONTEND_DIR / "package.json").exists():
        error("frontend/package.json not found")
        sys.exit(1)

    # Install deps if node_modules is missing
    if not (FRONTEND_DIR / "node_modules").exists():
        info("Installing npm dependencies …")
        run(["npm", "install"], cwd=FRONTEND_DIR)

    info("Running Vite production build …")
    run(["npm", "run", "build"], cwd=FRONTEND_DIR)

    index = FRONTEND_DIR / "dist" / "index.html"
    if not index.exists():
        error("Build finished but frontend/dist/index.html is missing")
        sys.exit(1)

    info(f"Frontend built → {FRONTEND_DIR / 'dist'}")


def step_pyinstaller(onefile: bool = False):
    header("Step 3/4 — Running PyInstaller")

    if not SPEC_FILE.exists():
        error(f"Spec file not found: {SPEC_FILE}")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC_FILE),
    ]

    # For onefile, we'll patch the spec dynamically instead of modifying it.
    # Simpler approach: pass --onefile which overrides the spec's COLLECT step.
    if onefile:
        warn("--onefile mode: producing single executable (larger, slower startup)")
        # PyInstaller CLI flags override spec settings when using .py entry,
        # but with a .spec they don't. We'll just note this for the user.
        warn("For true onefile, edit breachwright.spec: see comments in EXE/COLLECT blocks.")

    run(cmd)

    # Verify output
    if sys.platform == "win32":
        exe_name = "Breachwright.exe"
    else:
        exe_name = "Breachwright"

    output_exe = DIST_DIR / "Breachwright" / exe_name
    if output_exe.exists():
        size_mb = output_exe.stat().st_size / (1024 * 1024)
        info(f"Executable: {output_exe}  ({size_mb:.1f} MB)")
    else:
        error(f"Expected output not found: {output_exe}")
        sys.exit(1)


def step_smoke_test():
    header("Step 4/4 — Smoke test")

    if sys.platform == "win32":
        exe_name = "Breachwright.exe"
    else:
        exe_name = "Breachwright"

    output_exe = DIST_DIR / "Breachwright" / exe_name

    if not output_exe.exists():
        warn("Executable not found — skipping smoke test")
        return

    # Quick validation: check that the bundled data files exist
    bundle_root = DIST_DIR / "Breachwright"
    internal = bundle_root / "_internal"
    checks = {
        "frontend/dist/index.html": internal / "frontend" / "dist" / "index.html",
        "backend/alembic.ini":       internal / "backend" / "alembic.ini",
        "backend/alembic/versions":  internal / "backend" / "alembic" / "versions",
    }

    all_ok = True
    for label, path in checks.items():
        if path.exists():
            info(f"Bundled: {label}")
        else:
            warn(f"Missing: {label}")
            all_ok = False

    if all_ok:
        info("All smoke checks passed!")
    else:
        warn("Some bundled files are missing — the app may not run correctly.")

    # Count total files
    total_files = sum(1 for _ in bundle_root.rglob("*") if _.is_file())
    total_size  = sum(f.stat().st_size for f in bundle_root.rglob("*") if f.is_file())
    info(f"Bundle: {total_files} files, {total_size / (1024*1024):.1f} MB total")

    # Copy install.sh and uninstall.sh into the bundle for distribution
    for script in ("install.sh", "uninstall.sh", "README.md", "CHANGELOG.md"):
        src_path = PROJECT_ROOT / script
        if src_path.exists():
            import shutil
            shutil.copy2(str(src_path), str(bundle_root / script))

    # Copy icon files for installers
    for icon_file in ["icon.ico", "icon.png"]:
        icon_src = Path(project_root) / icon_file
        if icon_src.exists():
            shutil.copy2(str(icon_src), str(bundle_root / icon_file))
            print(f"  [+] Copied {icon_file}")
            info(f"Included: {script}")

    header("BUILD COMPLETE")
    print(f"\n  Output directory: {bundle_root}")
    print(f"  Run with:         ./{Path(exe_name)}\n")


def step_clean():
    header("Cleaning build artifacts")
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            info(f"Removing {d}")
            shutil.rmtree(d)
    info("Clean complete")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Build Breachwright distributable")
    parser.add_argument("--skip-frontend", action="store_true",
                        help="Skip the npm/Vite build step")
    parser.add_argument("--onefile", action="store_true",
                        help="Produce a single-file executable (slower startup)")
    parser.add_argument("--clean", action="store_true",
                        help="Remove build/ and dist/ before building")
    args = parser.parse_args()

    if args.clean:
        step_clean()

    step_validate()
    step_build_frontend(skip=args.skip_frontend)
    step_pyinstaller(onefile=args.onefile)
    step_smoke_test()


if __name__ == "__main__":
    main()


def step_update_launcher():
    """Update the system launcher to point at the new binary."""
    import stat
    launcher = Path.home() / ".local" / "bin" / "breachwright"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    exe = DIST_DIR / "Breachwright" / "Breachwright"
    launcher.write_text(f'#!/usr/bin/env bash\nexec "{exe}" "$@"\n')
    launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    info(f"Launcher updated: {launcher} → {exe}")

# Hook it into main()
_orig_main = main
def main():
    _orig_main()
    step_update_launcher()
main()


def step_package():
    """Create a distributable tarball from the bundle."""
    import tarfile
    header("Packaging")
    bundle = DIST_DIR / "Breachwright"
    if not bundle.exists():
        warn("No bundle found, skipping packaging")
        return
    # Read version from the binary's main.py
    version = "1.2.0"
    archive_name = f"breachwright-{version}-linux-x64.tar.gz"
    archive_path = DIST_DIR / archive_name
    info(f"Creating {archive_name} ...")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(str(bundle), arcname="Breachwright")
    size_mb = archive_path.stat().st_size / (1024*1024)
    info(f"Package: {archive_path} ({size_mb:.1f} MB)")
