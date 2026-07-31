from pathlib import Path
import sys
import unittest
import uuid

from fastapi import HTTPException
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.workflow.router import (
    MAX_COMPARISON_DETAILS_PER_STATUS,
    MAX_SNAPSHOT_SCANS,
    SnapshotCreate,
    _limited_keys,
    _read_snapshot_payload,
)


class SnapshotInputLimitTests(unittest.TestCase):
    def test_snapshot_requires_uuid_sized_scan_ids(self):
        with self.assertRaises(ValidationError):
            SnapshotCreate(label="Baseline", scan_ids=["not-a-scan-id"])

    def test_snapshot_caps_selected_scan_count(self):
        with self.assertRaises(ValidationError):
            SnapshotCreate(
                label="Too many scans",
                scan_ids=[str(uuid.uuid4()) for _ in range(MAX_SNAPSHOT_SCANS + 1)],
            )

    def test_snapshot_reader_stops_at_remaining_byte_budget(self):
        scan = ROOT / f".breachwright-snapshot-limit-{uuid.uuid4()}.jsonl"
        try:
            scan.write_bytes(b"1234")
            with self.assertRaises(HTTPException) as raised:
                _read_snapshot_payload(str(scan), scan.name, 3)
        finally:
            scan.unlink(missing_ok=True)
        self.assertEqual(raised.exception.status_code, 413)

    def test_snapshot_reader_reports_missing_stored_file(self):
        missing = ROOT / f".breachwright-missing-{uuid.uuid4()}.jsonl"
        with self.assertRaises(HTTPException) as raised:
            _read_snapshot_payload(str(missing), missing.name, 100)
        self.assertEqual(raised.exception.status_code, 409)

    def test_comparison_details_are_deterministic_and_bounded(self):
        keys = {
            f"{index:064x}"
            for index in range(MAX_COMPARISON_DETAILS_PER_STATUS + 25)
        }
        limited, truncated = _limited_keys(keys)
        self.assertEqual(len(limited), MAX_COMPARISON_DETAILS_PER_STATUS)
        self.assertEqual(limited, sorted(limited))
        self.assertEqual(truncated, 25)



if __name__ == "__main__":
    unittest.main()
