import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATA_DIR", str(ROOT / ".breachwright-setup-test"))

from app.auth.setup import _validate_setup_credentials
from app.auth.router import first_run_setup
from app.auth.schemas import UserCreate


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


class FirstRunSetupDurabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_administrator_is_committed_before_success(self):
        request = UserCreate(
            email="admin@example.com",
            password="correct-horse-battery-staple",
            display_name="Administrator",
        )
        db = AsyncMock()
        user = SimpleNamespace(email="admin@example.com")

        with (
            patch(
                "app.auth.router.get_active_user_count",
                AsyncMock(return_value=0),
            ),
            patch(
                "app.auth.router.create_user",
                AsyncMock(return_value=user),
            ),
        ):
            response = await first_run_setup(request, db)

        db.commit.assert_awaited_once()
        self.assertEqual(response["email"], "admin@example.com")


if __name__ == "__main__":
    unittest.main()
