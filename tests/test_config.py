import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATA_DIR", str(ROOT / ".breachwright-config-test"))

from app.config import get_data_dir


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
