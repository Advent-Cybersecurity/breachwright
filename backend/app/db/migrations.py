"""Database migration helpers used during application startup."""

import asyncio
import os

from alembic import command
from alembic.config import Config as AlembicConfig


def upgrade_database(base_dir: str, database_url: str) -> None:
    """Upgrade the configured database to the latest Alembic revision."""
    alembic_config = AlembicConfig(
        os.path.join(base_dir, "backend", "alembic.ini")
    )
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    alembic_config.set_main_option(
        "script_location",
        os.path.join(base_dir, "backend", "alembic"),
    )
    command.upgrade(alembic_config, "head")


async def run_migrations(
    base_dir: str,
    database_url: str,
    timeout_seconds: float = 30,
) -> None:
    """Run migrations off the event loop and propagate failures or timeouts."""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(upgrade_database, base_dir, database_url),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f"Database migration exceeded {timeout_seconds:g} seconds"
        ) from exc
