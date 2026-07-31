from collections import deque
import os
from pathlib import Path
import sys
import shutil
import unittest
import uuid

from fastapi import HTTPException


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
    read_job_artifact,
    TOOL_PRESETS,
)
from app.jobs.router import JobCreate, _build_job_command


def output_state() -> dict:
    return {
        "output_chunks": deque(),
        "output_length": 0,
        "output_truncated": False,
    }


class JobOutputTests(unittest.TestCase):
    def setUp(self):
        self.artifact_dir = ROOT / f".breachwright-job-artifact-{uuid.uuid4().hex}"
        self.artifact_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.artifact_dir, ignore_errors=True)

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

    def test_saved_tool_artifact_is_bounded_and_prioritized(self):
        (self.artifact_dir / "unrelated.bin").write_bytes(b"ignore me")
        (self.artifact_dir / "output.txt").write_text("nmap result", encoding="utf-8")
        self.assertEqual(
            read_job_artifact(str(self.artifact_dir)),
            ("output.txt", "nmap result"),
        )
        (self.artifact_dir / "output.jsonl").write_text('{"host":"example.test"}', encoding="utf-8")
        self.assertEqual(
            read_job_artifact(str(self.artifact_dir)),
            ("output.jsonl", '{"host":"example.test"}'),
        )
        (self.artifact_dir / "output.jsonl").write_text(
            "x" * (MAX_JOB_OUTPUT + 100),
            encoding="utf-8",
        )
        filename, content = read_job_artifact(str(self.artifact_dir))
        self.assertEqual(filename, "output.jsonl")
        self.assertLessEqual(len(content), MAX_JOB_OUTPUT + 40)
        self.assertTrue(content.endswith("[Saved tool artifact truncated]"))

    def test_nuclei_presets_emit_structured_jsonl(self):
        for preset in TOOL_PRESETS["nuclei"].values():
            self.assertIn("-jsonl", preset["cmd"])

    def test_preset_commands_are_built_from_validated_server_inputs(self):
        command = _build_job_command(JobCreate(
            engagement_id="engagement-1",
            tool="nmap",
            execution_mode="preset",
            preset="quick",
            target="10.20.30.0/24",
            ports="80,443,8000-8100",
            timing="T4",
        ))
        self.assertIn('"10.20.30.0/24"', command)
        self.assertIn("-p 80,443,8000-8100", command)
        self.assertIn("-T4", command)

    def test_preset_targets_cannot_inject_shell_commands(self):
        for target in (
            "example.test;whoami",
            "example.test && whoami",
            "$(whoami)",
            "`whoami`",
            "%COMSPEC%",
        ):
            with self.subTest(target=target), self.assertRaises(HTTPException) as caught:
                _build_job_command(JobCreate(
                    engagement_id="engagement-1",
                    tool="nmap",
                    execution_mode="preset",
                    preset="quick",
                    target=target,
                ))
            self.assertEqual(caught.exception.status_code, 422)

    def test_custom_commands_remain_an_explicit_mode(self):
        command = _build_job_command(JobCreate(
            engagement_id="engagement-1",
            tool="nmap",
            execution_mode="custom",
            command="nmap --version",
        ))
        self.assertEqual(command, "nmap --version")


if __name__ == "__main__":
    unittest.main()
