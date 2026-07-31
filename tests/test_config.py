import atexit
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

legacy_test_root = ROOT / ".breachwright-config-test"
if legacy_test_root.is_dir():
    shutil.rmtree(legacy_test_root)

config_test_root = Path(tempfile.mkdtemp(prefix="breachwright-config-test-"))
os.environ.setdefault("DATA_DIR", str(config_test_root))

from app.config import get_data_dir


def _cleanup_config_test_root() -> None:
    for handler in list(logging.getLogger().handlers):
        if (
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename).is_relative_to(config_test_root)
        ):
            logging.getLogger().removeHandler(handler)
            handler.close()
    shutil.rmtree(config_test_root, ignore_errors=True)


atexit.register(_cleanup_config_test_root)


class DataDirectoryTests(unittest.TestCase):
    def test_explicit_data_directory_controls_canonical_paths(self):
        configured = ROOT / ".data-directory-test"
        with patch.dict(os.environ, {"DATA_DIR": str(configured)}):
            self.assertEqual(get_data_dir(), str(configured.resolve()))

    def test_application_log_has_bounded_retention(self):
        handlers = [
            handler
            for handler in logging.getLogger().handlers
            if isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename).name == "breachwright.log"
        ]
        self.assertEqual(len(handlers), 1)
        self.assertEqual(handlers[0].maxBytes, 5 * 1024 * 1024)
        self.assertEqual(handlers[0].backupCount, 3)


if __name__ == "__main__":
    unittest.main()
