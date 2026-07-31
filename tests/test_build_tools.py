import subprocess
import unittest
from unittest.mock import patch

import build


class BuildToolTests(unittest.TestCase):
    @patch("build.subprocess.run")
    def test_supported_node_version_is_accepted(self, run):
        run.return_value = subprocess.CompletedProcess(
            ["node", "--version"],
            0,
            stdout="v20.19.2\n",
        )

        build.validate_node_version("node")

    @patch("build.subprocess.run")
    def test_unsupported_node_version_has_an_actionable_error(self, run):
        run.return_value = subprocess.CompletedProcess(
            ["node", "--version"],
            0,
            stdout="v18.20.8\n",
        )

        with self.assertRaisesRegex(SystemExit, "Node.js 20 or newer is required"):
            build.validate_node_version("node")


if __name__ == "__main__":
    unittest.main()
