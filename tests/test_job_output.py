from collections import deque
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATA_DIR", str(ROOT / ".breachwright-job-output-test"))

from app.jobs.runner import (
    MAX_JOB_OUTPUT,
    TRUNCATION_NOTICE,
    _append_job_output,
    _render_job_output,
)


def output_state() -> dict:
    return {
        "output_chunks": deque(),
        "output_length": 0,
        "output_truncated": False,
    }


class JobOutputTests(unittest.TestCase):
    def test_small_output_is_preserved(self):
        state = output_state()
        _append_job_output(state, "first\n")
        _append_job_output(state, "second\n")
        self.assertEqual(_render_job_output(state), "first\nsecond\n")

    def test_large_output_retains_a_bounded_tail(self):
        state = output_state()
        _append_job_output(state, "a" * 300_000)
        _append_job_output(state, "b" * 300_000)
        rendered = _render_job_output(state)
        self.assertEqual(len(rendered), MAX_JOB_OUTPUT)
        self.assertTrue(rendered.startswith(TRUNCATION_NOTICE))
        self.assertTrue(rendered.endswith("b" * 300_000))

    def test_one_oversized_chunk_is_bounded(self):
        state = output_state()
        _append_job_output(state, "x" * (MAX_JOB_OUTPUT * 2))
        rendered = _render_job_output(state)
        self.assertEqual(len(rendered), MAX_JOB_OUTPUT)
        self.assertTrue(rendered.startswith(TRUNCATION_NOTICE))


if __name__ == "__main__":
    unittest.main()
