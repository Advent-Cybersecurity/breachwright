# -*- mode: python ; coding: utf-8 -*-
"""
Breachwright PyInstaller Spec File (Windows and Linux)
=====================================================
Builds for Windows or Linux depending on the build machine.

Usage:
    cd frontend && npm run build && cd ..
    pyinstaller breachwright.spec
"""

import os
import sys
import platform
import importlib
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
)

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

PROJECT_ROOT = os.path.abspath(SPECPATH)

if IS_LINUX:
    _system_dist_packages = "/usr/lib/python3/dist-packages"
    if os.path.isdir(_system_dist_packages) and _system_dist_packages not in sys.path:
        sys.path.append(_system_dist_packages)

def proj(*parts):
    return os.path.join(PROJECT_ROOT, *parts)


# ========================== DATA / ASSET FILES =============================

datas = []

# 1. Vite frontend build output
_frontend_dist = proj("frontend", "dist")
if os.path.isdir(_frontend_dist):
    datas.append((_frontend_dist, os.path.join("frontend", "dist")))
else:
    print("WARNING: frontend/dist/ not found - run npm run build first!")

# 2. Alembic migrations + config
_alembic_dir = proj("backend", "alembic")
if os.path.isdir(_alembic_dir):
    datas.append((_alembic_dir, os.path.join("backend", "alembic")))

_alembic_ini = proj("backend", "alembic.ini")
if os.path.isfile(_alembic_ini):
    datas.append((_alembic_ini, "backend"))

# 3. Report templates
for _tpl_dir_name in ("templates", "report_templates", "assets"):
    _tpl_path = proj("backend", "app", "reports", _tpl_dir_name)
    if os.path.isdir(_tpl_path):
        datas.append((_tpl_path, os.path.join("backend", "app", "reports", _tpl_dir_name)))

# 4. Checklist data (non-Python files)
_checklists_dir = proj("backend", "app", "checklists")
if os.path.isdir(_checklists_dir):
    for f in os.listdir(_checklists_dir):
        if not f.endswith((".py", ".pyc", "__pycache__")):
            datas.append(
                (os.path.join(_checklists_dir, f),
                 os.path.join("backend", "app", "checklists"))
            )

# 5. Icons / assets
for _asset in ("icon.ico", "icon.png", "logo.png", "LICENSE", "LICENSE.txt", "THIRD_PARTY_NOTICES.md"):
    _p = proj(_asset)
    if os.path.isfile(_p):
        datas.append((_p, "."))


# ========================== HIDDEN IMPORTS =================================

hidden_imports = []

# -- Backend package tree
hidden_imports += collect_submodules("app")

# -- FastAPI / Starlette / Pydantic
hidden_imports += collect_submodules("fastapi")
hidden_imports += collect_submodules("starlette")
hidden_imports += collect_submodules("pydantic")
hidden_imports += collect_submodules("pydantic_core")

# -- Uvicorn
hidden_imports += collect_submodules("uvicorn")
hidden_imports += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

# -- HTTP parsing
for _mod in ("httptools", "h11", "wsproto", "websockets"):
    try:
        importlib.import_module(_mod)
        hidden_imports += collect_submodules(_mod)
    except ImportError:
        pass

# -- Async event loop
if not IS_WINDOWS:
    # uvloop doesn't work on Windows
    try:
        importlib.import_module("uvloop")
        hidden_imports += collect_submodules("uvloop")
    except ImportError:
        pass

# -- pywebview
hidden_imports += collect_submodules("webview")

# -- Platform-specific pywebview backends
if IS_WINDOWS:
    # EdgeChromium (WebView2) - pywebview auto-detects on Windows
    hidden_imports += [
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr_loader",
        "pythonnet",
    ]
    # pythonnet / clr dependencies
    for _mod in ("clr_loader", "pythonnet", "clr"):
        try:
            importlib.import_module(_mod)
            hidden_imports += collect_submodules(_mod)
        except ImportError:
            pass
else:
    # GTK/WebKit on Linux
    hidden_imports += collect_submodules("gi")
    hidden_imports += [
        "gi._gi",
        "gi.repository.Gtk",
        "gi.repository.GLib",
        "gi.repository.Gdk",
        "gi.repository.WebKit2",
        "gi.repository.GObject",
        "gi.repository.Gio",
    ]

# -- SQLAlchemy + Alembic
hidden_imports += collect_submodules("sqlalchemy")
hidden_imports += collect_submodules("alembic")
for _drv in ("aiosqlite", "sqlite3"):
    try:
        importlib.import_module(_drv)
        hidden_imports += collect_submodules(_drv)
    except ImportError:
        pass

# -- python-docx
for _mod in ("docx", "lxml", "lxml.etree", "lxml._elementpath"):
    try:
        importlib.import_module(_mod.split(".")[0])
        hidden_imports.append(_mod)
    except ImportError:
        pass
hidden_imports += collect_submodules("docx")

# -- AI / LLM libraries
for _mod in ("openai", "anthropic", "tiktoken", "httpx", "jwt"):
    try:
        importlib.import_module(_mod)
        hidden_imports += collect_submodules(_mod)
    except ImportError:
        pass

# -- Common deps
for _mod in (
    "multipart",
    "jose",
    "passlib",
    "bcrypt",
    "email_validator",
    "dotenv",
    "yaml",
    "jinja2",
    "markupsafe",
    "anyio",
    "sniffio",
    "certifi",
    "charset_normalizer",
    "idna",
    "pydantic_settings",
):
    try:
        importlib.import_module(_mod)
        hidden_imports += collect_submodules(_mod)
    except ImportError:
        pass

# Deduplicate and keep dependency test/type-checker packages out of the
# distributable. Broad submodule discovery is useful for plugin-style runtime
# imports, but it otherwise pulls in modules that only dependency maintainers
# use.
_non_runtime_segments = {
    "_hypothesis_plugin",
    "_tests",
    "mypy",
    "pytest_plugin",
    "test",
    "testing",
    "tests",
    "tox_support",
}
hidden_imports = sorted(
    {
        name
        for name in hidden_imports
        if not _non_runtime_segments.intersection(name.split("."))
    }
)


# ========================== EXTRA DATA FILES ===============================

_extra_datas = []
for _pkg in ("certifi", "email_validator", "docx", "jinja2", "alembic"):
    try:
        _extra_datas += collect_data_files(_pkg)
    except Exception:
        pass
datas += _extra_datas

# Platform-specific data
if IS_LINUX:
    # PyGObject typelibs
    try:
        import gi
        _gi_path = os.path.dirname(gi.__file__)
        datas.append((_gi_path, "gi"))
    except ImportError:
        pass
    for _typelib_dir in ("/usr/lib/x86_64-linux-gnu/girepository-1.0", "/usr/lib/girepository-1.0"):
        if os.path.isdir(_typelib_dir):
            datas.append((_typelib_dir, "gi_typelibs"))
            break

if IS_WINDOWS:
    # WebView2 runtime files if present
    try:
        import clr_loader
        _clr_path = os.path.dirname(clr_loader.__file__)
        datas.append((_clr_path, "clr_loader"))
    except ImportError:
        pass


# ========================== ANALYSIS =======================================

_excludes = [
    "matplotlib", "scipy", "numpy", "pandas",
    "IPython", "jupyter", "notebook",
    "pytest", "unittest",
    "boto3", "botocore", "s3transfer", "awscrt",
    "setuptools", "pip", "wheel", "pkg_resources",
    "test", "lib2to3", "ensurepip",
    "django",
    "PyQt5", "PyQt6", "PySide2", "PySide6",
    "pygame", "PIL", "Pillow",
]

# Don't exclude GTK on Linux or pythonnet on Windows
if IS_WINDOWS:
    _excludes += ["gi", "gi.repository"]
else:
    _excludes += ["clr_loader", "pythonnet", "clr", "win32api", "win32com"]

a = Analysis(
    [proj("run.py")],
    pathex=[
        PROJECT_ROOT,
        proj("backend"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[proj("runtime_hook.py")],
    excludes=_excludes,
    noarchive=False,
)


# ========================== BUNDLE =========================================

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Breachwright",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=proj("icon.ico") if os.path.isfile(proj("icon.ico")) else None,
)

cli_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BreachwrightCLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=proj("icon.ico") if os.path.isfile(proj("icon.ico")) else None,
)

coll = COLLECT(
    exe,
    cli_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Breachwright",
)
