import os
import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check_public_tree_hygiene.py"
MAX_DIAGNOSTIC_CHARS = 4_000


class PublicTreeHygieneTests(unittest.TestCase):
    def run_guard(self, *arguments: str) -> None:
        environment = os.environ.copy()
        for name in tuple(environment):
            if name.startswith("GIT_CONFIG_"):
                environment.pop(name)
        completed = subprocess.run(
            [sys.executable, str(GUARD), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            timeout=30,
        )
        diagnostic = (completed.stdout + completed.stderr)[-MAX_DIAGNOSTIC_CHARS:]
        self.assertEqual(0, completed.returncode, diagnostic)

    def test_guard_self_test(self):
        self.run_guard("--self-test")

    def test_live_git_index_audit(self):
        self.run_guard()


if __name__ == "__main__":
    unittest.main()
