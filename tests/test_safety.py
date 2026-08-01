from pathlib import Path
import shutil
import sys
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.safety import app_data_directory, canonical_uuid, safe_log_value


class SafetyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = ROOT / f".breachwright-safety-{uuid.uuid4().hex}"
        self.data_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_app_data_directories_use_canonical_uuid_components(self):
        record_id = str(uuid.uuid4())
        path = app_data_directory(
            str(self.data_dir),
            "uploads",
            record_id.upper(),
        )
        expected = self.data_dir.resolve() / "uploads" / record_id
        self.assertEqual(path, expected)

    def test_app_data_directories_reject_non_uuid_components(self):
        for value in ("../outside", "not-a-uuid", "id/child"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                app_data_directory(str(self.data_dir), "uploads", value)

    def test_canonical_uuid_rejects_path_control_input(self):
        with self.assertRaises(ValueError):
            canonical_uuid("00000000-0000-0000-0000-000000000000/../outside")

    def test_safe_log_value_is_single_line_and_bounded(self):
        value = safe_log_value("tool\r\nforged\tentry\u2028next", max_length=21)
        self.assertEqual(value, "tool  forged entry ne")
        self.assertNotIn("\n", value)
        self.assertNotIn("\r", value)
