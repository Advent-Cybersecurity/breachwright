"""
Breachwright — PyInstaller Runtime Hook
========================================
Runs *before* any application code.  Sets environment variables and sys.path
so that the frozen bundle can locate its bundled data (frontend dist, alembic
migrations, templates, etc.) using the same relative paths as development.

PyInstaller sets ``sys._MEIPASS`` to the temporary extraction directory
(onefile) or the application directory (onedir).
"""

import os
import sys

def _get_base_dir():
    """Return the base directory where bundled data lives."""
    # PyInstaller >= 5 sets sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    # Fallback: directory of the entry-point script
    return os.path.dirname(os.path.abspath(sys.argv[0]))


BASE_DIR = _get_base_dir()

# ---------------------------------------------------------------------------
# 1.  Make sure ``backend`` is importable
# ---------------------------------------------------------------------------
_backend_dir = os.path.join(BASE_DIR, "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Also keep the root on the path (for ``import backend.app…`` style imports)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ---------------------------------------------------------------------------
# 2.  Expose BASE_DIR through an env-var so application code can read it
#     without importing this file directly.
# ---------------------------------------------------------------------------
os.environ["BREACHWRIGHT_BASE_DIR"] = BASE_DIR
os.environ["BREACHWRIGHT_FROZEN"] = "1" if getattr(sys, "frozen", False) else "0"

# ---------------------------------------------------------------------------
# 3.  Point Alembic at the bundled alembic.ini + migrations
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "BREACHWRIGHT_ALEMBIC_INI",
    os.path.join(BASE_DIR, "backend", "alembic.ini"),
)
os.environ.setdefault(
    "BREACHWRIGHT_ALEMBIC_DIR",
    os.path.join(BASE_DIR, "backend", "alembic"),
)

# ---------------------------------------------------------------------------
# 4.  Set a user-writable data directory for the DB, logs, config, etc.
#     (The frozen bundle itself is read-only on most platforms.)
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    _appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    _user_data = os.path.join(_appdata, "Breachwright")
elif sys.platform == "darwin":
    _user_data = os.path.join(
        os.path.expanduser("~"), "Library", "Application Support", "Breachwright"
    )
else:
    _user_data = os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share")),
        "breachwright",
    )

os.makedirs(_user_data, exist_ok=True)
os.environ.setdefault("DATA_DIR", _user_data)
os.environ.setdefault("BREACHWRIGHT_USER_DATA", _user_data)

# ---------------------------------------------------------------------------
# 5.  Sensible defaults for the DB location (SQLite)
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "BREACHWRIGHT_DB_PATH",
    os.path.join(_user_data, "breachwright.db"),
)

# ---------------------------------------------------------------------------
# 6.  Frontend dist path (for FastAPI's StaticFiles mount)
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "BREACHWRIGHT_FRONTEND_DIST",
    os.path.join(BASE_DIR, "frontend", "dist"),
)
