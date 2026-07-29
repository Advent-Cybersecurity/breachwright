"""
Breachwright — Path Helper
===========================
Import this module anywhere in the backend to resolve paths that work
identically in development (``python run.py``) **and** inside a
PyInstaller-frozen bundle.

Usage::

    from backend.app.path_helper import paths

    db_path       = paths.db_path          # user-writable SQLite location
    frontend_dist = paths.frontend_dist    # Vite build output
    alembic_ini   = paths.alembic_ini
    alembic_dir   = paths.alembic_dir
    user_data     = paths.user_data_dir    # writable dir for logs / config
    base          = paths.base_dir         # project root or _MEIPASS
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dataclasses import dataclass, field


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _resolve_base_dir() -> Path:
    """
    In a frozen build  → sys._MEIPASS  (extraction / bundle dir)
    In development     → project root  (parent of backend/)
    """
    if _is_frozen():
        return Path(sys._MEIPASS)
    # In dev, this file lives at  <project>/backend/app/path_helper.py
    return Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class BreachwritePaths:
    """Centralised path resolution for every runtime mode."""

    base_dir: Path = field(default_factory=_resolve_base_dir)

    # ------------------------------------------------------------------
    # Derived paths
    # ------------------------------------------------------------------
    @property
    def frozen(self) -> bool:
        return _is_frozen()

    # -- Frontend -------------------------------------------------------
    @property
    def frontend_dist(self) -> Path:
        env = os.environ.get("BREACHWRIGHT_FRONTEND_DIST")
        if env:
            return Path(env)
        return self.base_dir / "frontend" / "dist"

    # -- Alembic --------------------------------------------------------
    @property
    def alembic_ini(self) -> Path:
        env = os.environ.get("BREACHWRIGHT_ALEMBIC_INI")
        if env:
            return Path(env)
        return self.base_dir / "backend" / "alembic.ini"

    @property
    def alembic_dir(self) -> Path:
        env = os.environ.get("BREACHWRIGHT_ALEMBIC_DIR")
        if env:
            return Path(env)
        return self.base_dir / "backend" / "alembic"

    # -- User-writable data directory -----------------------------------
    @property
    def user_data_dir(self) -> Path:
        env = os.environ.get("BREACHWRIGHT_USER_DATA")
        if env:
            p = Path(env)
        elif sys.platform == "win32":
            appdata = os.environ.get("LOCALAPPDATA", str(Path.home()))
            p = Path(appdata) / "Breachwright"
        elif sys.platform == "darwin":
            p = Path.home() / "Library" / "Application Support" / "Breachwright"
        else:
            xdg = os.environ.get(
                "XDG_DATA_HOME", str(Path.home() / ".local" / "share")
            )
            p = Path(xdg) / "breachwright"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # -- Database -------------------------------------------------------
    @property
    def db_path(self) -> Path:
        env = os.environ.get("BREACHWRIGHT_DB_PATH")
        if env:
            return Path(env)
        return self.user_data_dir / "breachwright.db"

    @property
    def db_url(self) -> str:
        """SQLAlchemy-compatible connection string."""
        return f"sqlite:///{self.db_path}"

    @property
    def async_db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    # -- Logs -----------------------------------------------------------
    @property
    def log_dir(self) -> Path:
        p = self.user_data_dir / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # -- Reports / generated output -------------------------------------
    @property
    def reports_output_dir(self) -> Path:
        p = self.user_data_dir / "reports"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # -- Report templates bundled with the app --------------------------
    @property
    def report_templates_dir(self) -> Path:
        return self.base_dir / "backend" / "app" / "reports" / "templates"

    # -- Settings / config file -----------------------------------------
    @property
    def settings_file(self) -> Path:
        return self.user_data_dir / "settings.json"


# Singleton — import ``paths`` everywhere
paths = BreachwritePaths()
