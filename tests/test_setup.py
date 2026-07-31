import os
from pathlib import Path
import sys
import unittest

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATA_DIR", str(ROOT / ".breachwright-setup-test"))

from app.auth.setup import _validate_setup_credentials


class SetupCredentialTests(unittest.TestCase):
    def test_valid_credentials_are_normalized(self):
        credentials = _validate_setup_credentials(
            "  ADMIN@Example.com ",
            "  Primary Admin  ",
            "correct-horse-battery-staple",
        )
        self.assertEqual(credentials["email"], "admin@example.com")
        self.assertEqual(credentials["display_name"], "Primary Admin")

    def test_setup_rejects_invalid_email_and_weak_password(self):
        with self.assertRaises(ValidationError):
            _validate_setup_credentials(
                "not-an-email",
                "Admin",
                "correct-horse-battery-staple",
            )
        with self.assertRaises(ValidationError):
            _validate_setup_credentials(
                "admin@example.com",
                "Admin",
                "too-short",
            )

    def test_setup_rejects_blank_name_and_oversized_bcrypt_password(self):
        with self.assertRaises(ValidationError):
            _validate_setup_credentials(
                "admin@example.com",
                "   ",
                "correct-horse-battery-staple",
            )
        with self.assertRaises(ValidationError):
            _validate_setup_credentials(
                "admin@example.com",
                "Admin",
                "\u00e9" * 40,
            )


if __name__ == "__main__":
    unittest.main()
