# -*- mode: python ; coding: utf-8 -*-
"""
Breachwright PyInstaller Spec File
===================================
Packages the pywebview + uvicorn + FastAPI desktop application.

Usage:
    pyinstaller breachwright.spec

Prerequisites:
    1. Build the frontend first:  cd frontend && npm run build
    2. Install PyInstaller:       pip install pyinstaller
    3. Run from project root:     pyinstaller breachwright.spec
"""

import os
import sys
import importlib
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    collect_all,
)

# ---------------------------------------------------------------------------
# Project root = directory containing this spec file
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(SPECPATH)

# ---------------------------------------------------------------------------
# Helper: resolve a project-relative path
# ---------------------------------------------------------------------------
def proj(*parts):
    return os.path.join(PROJECT_ROOT, *parts)


# ========================== DATA / ASSET FILES =============================

datas = []

# 1. Vite frontend build output
_frontend_dist = proj("frontend", "dist")
if os.path.isdir(_frontend_dist):
    datas.append((_frontend_dist, os.path.join("frontend", "dist")))
else:
    print("⚠  WARNING: frontend/dist/ not found — run `npm run build` first!")

# 2. Alembic migrations + config
_alembic_dir = proj("backend", "alembic")
if os.path.isdir(_alembic_dir):
    datas.append((_alembic_dir, os.path.join("backend", "alembic")))

_alembic_ini = proj("backend", "alembic.ini")
if os.path.isfile(_alembic_ini):
    datas.append((_alembic_ini, "backend"))

# 3. Any DOCX / report templates (common patterns)
for _tpl_dir_name in ("templates", "report_templates", "assets"):
    _tpl_path = proj("backend", "app", "reports", _tpl_dir_name)
    if os.path.isdir(_tpl_path):
        datas.append((_tpl_path, os.path.join("backend", "app", "reports", _tpl_dir_name)))

# 4. Checklist / methodology data shipped as package data (if any non-.py files)
_checklists_dir = proj("backend", "app", "checklists")
if os.path.isdir(_checklists_dir):
    for f in os.listdir(_checklists_dir):
        if not f.endswith((".py", ".pyc", "__pycache__")):
            datas.append(
                (os.path.join(_checklists_dir, f),
                 os.path.join("backend", "app", "checklists"))
            )

# 5. Static / misc assets at project root (icons, logos, etc.)
for _asset in ("icon.ico", "icon.png", "logo.png", "LICENSE", "LICENSE.txt", "THIRD_PARTY_NOTICES.md"):
    _p = proj(_asset)
    if os.path.isfile(_p):
        datas.append((_p, "."))


# ========================== HIDDEN IMPORTS =================================

hidden_imports = []

# -- Collect the ENTIRE backend package tree automatically ------------------
hidden_imports += collect_submodules("backend")

# -- FastAPI / Starlette / Pydantic -----------------------------------------
hidden_imports += collect_submodules("fastapi")
hidden_imports += collect_submodules("starlette")
hidden_imports += collect_submodules("pydantic")
hidden_imports += collect_submodules("pydantic_core")

# -- Uvicorn & its transitive deps ------------------------------------------
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

# -- HTTP parsing libraries (uvicorn optional deps) -------------------------
for _mod in ("httptools", "h11", "wsproto", "websockets"):
    try:
        importlib.import_module(_mod)
        hidden_imports += collect_submodules(_mod)
    except ImportError:
        pass

# -- Async event-loop extras ------------------------------------------------
for _mod in ("uvloop",):
    try:
        importlib.import_module(_mod)
        hidden_imports += collect_submodules(_mod)
    except ImportError:
        pass

# -- pywebview ---------------------------------------------------------------
hidden_imports += collect_submodules("webview")

# -- PyGObject / GTK (pywebview backend) ------------------------------------
hidden_imports += collect_submodules("gi")
hidden_imports += ["gi._gi", "gi.repository.Gtk", "gi.repository.GLib", "gi.repository.Gdk", "gi.repository.WebKit2", "gi.repository.GObject", "gi.repository.Gio"]

# -- SQLAlchemy + Alembic ----------------------------------------------------
hidden_imports += collect_submodules("sqlalchemy")
hidden_imports += collect_submodules("alembic")
# Common DB drivers
for _drv in ("aiosqlite", "sqlite3", "asyncpg", "psycopg2"):
    try:
        importlib.import_module(_drv)
        hidden_imports += collect_submodules(_drv)
    except ImportError:
        pass

# -- python-docx (report generation) ----------------------------------------
for _mod in ("docx", "lxml", "lxml.etree", "lxml._elementpath"):
    try:
        importlib.import_module(_mod.split(".")[0])
        hidden_imports.append(_mod)
    except ImportError:
        pass
hidden_imports += collect_submodules("docx")

# -- AI / LLM libraries (commonly used) -------------------------------------
for _mod in ("openai", "anthropic", "tiktoken", "httpx", "jwt"):
    try:
        importlib.import_module(_mod)
        hidden_imports += collect_submodules(_mod)
    except ImportError:
        pass

# -- Other common deps -------------------------------------------------------
for _mod in (
    "multipart",          # python-multipart (FastAPI file uploads)
    "jose",               # python-jose (JWT)
    "passlib",            # password hashing
    "bcrypt",
    "email_validator",
    "dotenv",             # python-dotenv
    "yaml",               # PyYAML
    "jinja2",
    "markupsafe",
    "anyio",
    "sniffio",
    "certifi",
    "charset_normalizer",
    "idna",
):
    try:
        importlib.import_module(_mod)
        hidden_imports += collect_submodules(_mod)
    except ImportError:
        pass

# Deduplicate
hidden_imports = sorted(set(hidden_imports))


# ========================== COLLECT EXTRA DATA =============================
# Some packages ship data files that PyInstaller misses.

_extra_datas = []
for _pkg in ("certifi", "email_validator", "docx", "jinja2", "alembic"):
    try:
        _extra_datas += collect_data_files(_pkg)
    except Exception:
        pass

datas += _extra_datas

# PyGObject typelibs
try:
    import gi
    _gi_path = os.path.dirname(gi.__file__)
    datas.append((_gi_path, "gi"))
except ImportError:
    pass

# System typelibs
for _typelib_dir in ("/usr/lib/x86_64-linux-gnu/girepository-1.0", "/usr/lib/girepository-1.0"):
    if os.path.isdir(_typelib_dir):
        datas.append((_typelib_dir, "gi_typelibs"))
        break


# ========================== ANALYSIS =======================================

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
    excludes=[
        # ---- Large packages not needed ----
        "tkinter", "_tkinter",
        "matplotlib", "matplotlib.backends",
        "scipy",
        "numpy", "numpy.testing",
        "pandas",
        "IPython", "jupyter", "notebook",
        "pytest", "unittest",
        # ---- boto3/botocore (huge, ~80MB+ of JSON) ----
        "boto3", "botocore", "s3transfer", "awscrt",
        # ---- Dev/test tools ----
        "setuptools", "pip", "wheel", "pkg_resources",
        # ---- Unused stdlib ----
        "test", "lib2to3", "ensurepip",
        "django", "django.db", "django.core", "django.contrib", "django.template",
        "PyQt5", "PyQt6", "PySide2", "PySide6",
        "pygame",
        "PIL", "Pillow",
        "passlib.tests", "sqlalchemy.testing", "aiosqlite.tests",
        "py", "pytz",
        "pydoc_data", "doctest",
    ],
    noarchive=False,
)


# ========================== BUNDLE =========================================

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],                     # empty → onedir mode  (remove for onefile)
    exclude_binaries=True,  # True  → onedir mode
    name="Breachwright",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No console window (GUI app via pywebview)
    # Uncomment and set icon path if available:
    icon=proj("icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Breachwright",
)
