import asyncio
import os
import sys
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.db.migrations import run_migrations


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_migration_failure_is_propagated(self):
        with patch(
            "app.db.migrations.upgrade_database",
            side_effect=ValueError("broken revision"),
        ):
            with self.assertRaisesRegex(ValueError, "broken revision"):
                await run_migrations(ROOT, "sqlite+aiosqlite:///unused.db")

    async def test_migration_timeout_is_propagated(self):
        def slow_upgrade(*_args):
            import time
            time.sleep(0.1)

        with patch("app.db.migrations.upgrade_database", side_effect=slow_upgrade):
            with self.assertRaisesRegex(
                RuntimeError,
                "Database migration exceeded",
            ):
                await run_migrations(
                    ROOT,
                    "sqlite+aiosqlite:///unused.db",
                    timeout_seconds=0.01,
                )

    async def test_successful_migration_returns_normally(self):
        with patch("app.db.migrations.upgrade_database") as upgrade:
            await run_migrations(ROOT, "sqlite+aiosqlite:///unused.db")
            upgrade.assert_called_once()


if __name__ == "__main__":
    unittest.main()
