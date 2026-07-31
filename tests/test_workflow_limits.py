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
    _csv_safe,
    _limited_keys,
    _normalize_host,
    _read_snapshot_payload,
    _search_pattern,
)


class SnapshotInputLimitTests(unittest.TestCase):
    def test_csv_formula_detection_ignores_leading_whitespace(self):
        self.assertEqual(_csv_safe("  =HYPERLINK(\"x\")", False), "'  =HYPERLINK(\"x\")")
        self.assertEqual(_csv_safe("\n@SUM(1,1)", False), "'\n@SUM(1,1)")

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

    def test_asset_host_normalization_handles_urls_ports_and_ip_literals(self):
        self.assertEqual(_normalize_host("HTTPS://App.Example.Test:8443/admin"), "app.example.test")
        self.assertEqual(_normalize_host("app.example.test.:443/path"), "app.example.test")
        self.assertEqual(_normalize_host("[2001:0db8::1]:443"), "2001:db8::1")
        self.assertEqual(_normalize_host(""), "")

    def test_search_pattern_treats_sql_wildcards_as_literal_text(self):
        self.assertEqual(_search_pattern(r"rate_100%\done"), r"%rate\_100\%\\done%")



if __name__ == "__main__":
    unittest.main()
