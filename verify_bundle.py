#!/usr/bin/env python3
"""Verify the Breachwright PyInstaller bundle has everything it needs."""
import os
import sys

BUNDLE = os.path.expanduser("~/Desktop/breachwright/dist/Breachwright")
INTERNAL = os.path.join(BUNDLE, "_internal")

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
NC = "\033[0m"

passed = 0
warned = 0
failed = 0

def check(label, path):
    global passed, failed
    if os.path.exists(path):
        print(f"  {GREEN}✓{NC} {label}")
        passed += 1
        return True
    else:
        print(f"  {RED}✗{NC} {label}  →  {path}")
        failed += 1
        return False

def warn_check(label, path):
    global passed, warned
    if os.path.exists(path):
        print(f"  {GREEN}✓{NC} {label}")
        passed += 1
    else:
        print(f"  {YELLOW}⚠{NC} {label} (optional)")
        warned += 1

print(f"\n{BOLD}Breachwright Bundle Verification{NC}")
print(f"Bundle: {BUNDLE}")
print(f"Internal: {INTERNAL}\n")

# Executable
print(f"{BOLD}── Executable ──{NC}")
exe = os.path.join(BUNDLE, "Breachwright")
check("Breachwright binary", exe)
if os.path.exists(exe):
    size_mb = os.path.getsize(exe) / (1024*1024)
    print(f"       Size: {size_mb:.1f} MB")

# Frontend
print(f"\n{BOLD}── Frontend ──{NC}")
check("frontend/dist/index.html", os.path.join(INTERNAL, "frontend", "dist", "index.html"))
check("frontend/dist/assets/", os.path.join(INTERNAL, "frontend", "dist", "assets"))

# Count JS/CSS files
assets_dir = os.path.join(INTERNAL, "frontend", "dist", "assets")
if os.path.isdir(assets_dir):
    js_files = [f for f in os.listdir(assets_dir) if f.endswith('.js')]
    css_files = [f for f in os.listdir(assets_dir) if f.endswith('.css')]
    print(f"       JS bundles: {len(js_files)}, CSS bundles: {len(css_files)}")

# Alembic
print(f"\n{BOLD}── Database Migrations ──{NC}")
check("backend/alembic.ini", os.path.join(INTERNAL, "backend", "alembic.ini"))
check("backend/alembic/env.py", os.path.join(INTERNAL, "backend", "alembic", "env.py"))
check("backend/alembic/versions/", os.path.join(INTERNAL, "backend", "alembic", "versions"))

versions_dir = os.path.join(INTERNAL, "backend", "alembic", "versions")
if os.path.isdir(versions_dir):
    migrations = [f for f in os.listdir(versions_dir) if f.endswith('.py') and not f.startswith('__')]
    print(f"       Migration files: {len(migrations)}")

# Key Python modules (spot check inside _internal)
print(f"\n{BOLD}── Python Modules ──{NC}")
for mod in ["fastapi", "uvicorn", "sqlalchemy", "alembic", "docx", "webview", "pydantic"]:
    warn_check(f"{mod} package", os.path.join(INTERNAL, mod))

# GTK / gi (critical for pywebview)
print(f"\n{BOLD}── GTK / PyGObject ──{NC}")
# gi could be in multiple locations
gi_found = False
for candidate in [
    os.path.join(INTERNAL, "gi"),
    os.path.join(INTERNAL, "lib", "gi"),
]:
    if os.path.exists(candidate):
        gi_found = True
        print(f"  {GREEN}✓{NC} gi package  →  {candidate}")
        passed += 1
        break
if not gi_found:
    # Check if gi is importable from system
    print(f"  {YELLOW}⚠{NC} gi not in bundle (will use system gi via --system-site-packages)")
    warned += 1

# User data directory
print(f"\n{BOLD}── User Data ──{NC}")
user_data = os.path.expanduser("~/.local/share/breachwright")
warn_check("User data dir exists", user_data)
warn_check("Database file", os.path.join(user_data, "breachwright.db"))

# Bundle stats
print(f"\n{BOLD}── Bundle Stats ──{NC}")
total_files = 0
total_size = 0
for root, dirs, files in os.walk(BUNDLE):
    for f in files:
        fp = os.path.join(root, f)
        total_files += 1
        total_size += os.path.getsize(fp)
print(f"  Total files: {total_files}")
print(f"  Total size:  {total_size / (1024*1024):.1f} MB")

# Summary
print(f"\n{BOLD}── Summary ──{NC}")
print(f"  {GREEN}Passed: {passed}{NC}  {YELLOW}Warnings: {warned}{NC}  {RED}Failed: {failed}{NC}")
if failed == 0:
    print(f"\n  {GREEN}{BOLD}Bundle looks good!{NC}\n")
else:
    print(f"\n  {RED}{BOLD}Fix {failed} failure(s) before distributing.{NC}\n")

sys.exit(1 if failed > 0 else 0)
