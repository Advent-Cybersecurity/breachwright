#!/usr/bin/env python3
"""Verify a built Breachwright directory without launching it."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bundle",
        nargs="?",
        type=Path,
        default=PROJECT_ROOT / "dist" / "Breachwright",
        help="Path to the extracted or freshly built Breachwright directory.",
    )
    args = parser.parse_args()
    bundle = args.bundle.expanduser().resolve()
    internal = bundle / "_internal"
    passed = 0
    failed = 0

    def check(label: str, path: Path) -> bool:
        nonlocal passed, failed
        if path.exists():
            print(f"  [OK]   {label}")
            passed += 1
            return True
        print(f"  [FAIL] {label}: {path}")
        failed += 1
        return False

    print("Breachwright bundle verification")
    print(f"Bundle: {bundle}")
    if not bundle.is_dir():
        print("[FAIL] Bundle directory does not exist")
        return 1

    windows = (bundle / "Breachwright.exe").is_file()
    executable = bundle / ("Breachwright.exe" if windows else "Breachwright")
    cli = bundle / ("BreachwrightCLI.exe" if windows else "BreachwrightCLI")
    installer = bundle / ("install-windows.bat" if windows else "install.sh")
    uninstaller = bundle / ("uninstall-windows.bat" if windows else "uninstall.sh")

    print("\nExecutables")
    check("desktop executable", executable)
    check("command-line executable", cli)

    print("\nRuntime data")
    check("frontend index", internal / "frontend" / "dist" / "index.html")
    assets = internal / "frontend" / "dist" / "assets"
    if check("frontend assets", assets):
        javascript = len(list(assets.glob("*.js")))
        stylesheets = len(list(assets.glob("*.css")))
        if javascript == 0 or stylesheets == 0:
            print("  [FAIL] Frontend assets do not contain JavaScript and CSS")
            failed += 1
        else:
            print(f"         {javascript} JavaScript, {stylesheets} CSS bundle(s)")
    check("Alembic configuration", internal / "backend" / "alembic.ini")
    check("Alembic environment", internal / "backend" / "alembic" / "env.py")
    migrations = internal / "backend" / "alembic" / "versions"
    if check("database migrations", migrations):
        migration_count = len([
            path for path in migrations.glob("*.py")
            if not path.name.startswith("__")
        ])
        if migration_count == 0:
            print("  [FAIL] No database migration files were bundled")
            failed += 1
        else:
            print(f"         {migration_count} migration file(s)")

    print("\nDistribution files")
    for name in ("VERSION", "README.md", "LICENSE", "NOTICE", "SECURITY.md"):
        check(name, bundle / name)
    check(installer.name, installer)
    check(uninstaller.name, uninstaller)
    check("data-safety guide", bundle / "docs" / "DATA_SAFETY.md")
    check("dependency license directory", bundle / "THIRD_PARTY_LICENSES")

    unexpected = [
        path.relative_to(bundle)
        for path in bundle.rglob("*")
        if path.is_file()
        and (
            path.name == ".env"
            or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".log"}
        )
    ]
    if unexpected:
        print("\n  [FAIL] Runtime data or secrets are present:")
        for path in unexpected[:20]:
            print(f"         {path}")
        failed += 1
    else:
        print("\n  [OK]   No .env, database, or log files are bundled")
        passed += 1

    files = [path for path in bundle.rglob("*") if path.is_file()]
    total_bytes = sum(path.stat().st_size for path in files)
    print("\nSummary")
    print(f"  Files: {len(files)}")
    print(f"  Bytes: {total_bytes}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
