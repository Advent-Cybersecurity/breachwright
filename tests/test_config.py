import os
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


if __name__ == "__main__":
    unittest.main()
