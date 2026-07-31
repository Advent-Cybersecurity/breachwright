import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.version import is_newer_version


class VersionTests(unittest.TestCase):
    def test_older_release_is_not_an_update_for_release_candidate(self):
        self.assertFalse(is_newer_version("2.0.0", "2.1.0-rc.1"))

    def test_final_release_is_newer_than_its_release_candidate(self):
        self.assertTrue(is_newer_version("2.1.0", "2.1.0-rc.1"))

    def test_newer_patch_and_major_are_updates(self):
        self.assertTrue(is_newer_version("2.1.1", "2.1.0"))
        self.assertTrue(is_newer_version("3.0.0", "2.9.9"))

    def test_equal_or_invalid_versions_are_not_updates(self):
        self.assertFalse(is_newer_version("2.1.0", "2.1.0"))
        self.assertFalse(is_newer_version("", "2.1.0"))
        self.assertFalse(is_newer_version("release-2", "2.1.0"))


if __name__ == "__main__":
    unittest.main()
