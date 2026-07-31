import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


def get_data_dir() -> str:
    """Determine the application data directory based on platform."""
    configured = os.environ.get("DATA_DIR")
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "Breachwright")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Breachwright")
    else:
        xdg = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        return os.path.join(xdg, "breachwright")



DEFAULT_DATA_DIR = get_data_dir()


def _get_canonical_env_path() -> str:
    """The ONE location where .env lives. No ambiguity."""
    return os.path.join(get_data_dir(), ".env")


def _migrate_env_file():
    """Move .env from old locations to the canonical path (one-time migration)."""
    canonical = _get_canonical_env_path()
    if os.path.exists(canonical):
        return canonical

    # Old locations to check (in priority order)
    old_locations = [
        Path(get_data_dir()) / "app" / ".env",
        Path.home() / ".local" / "share" / "breachwright" / "app" / ".env",
        Path.home() / ".local" / "share" / "app" / ".env",
    ]

    # In dev mode, also check project directories
    if not getattr(sys, 'frozen', False):
        old_locations += [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent.parent.parent / ".env",
            Path(__file__).resolve().parent.parent / ".env",
        ]

    for old_path in old_locations:
        if old_path.is_file():
            import shutil
            os.makedirs(os.path.dirname(canonical), exist_ok=True)
            shutil.copy2(str(old_path), canonical)
            logging.getLogger(__name__).info(
                "Migrated .env from %s to %s", old_path, canonical
            )
            return canonical

    return None


def find_env_file() -> Optional[str]:
    """Returns the canonical .env path, migrating from old locations if needed."""
    return _migrate_env_file() or (
        _get_canonical_env_path() if os.path.exists(_get_canonical_env_path()) else None
    )


ENV_FILE = find_env_file()


class Settings(BaseSettings):
    # Database
    database_url: Optional[str] = None

    # Application
    cors_origins: str = "http://localhost,http://127.0.0.1"
    host: str = "127.0.0.1"
    port: int = 13370

    # AI Provider
    ai_provider: str = "anthropic"
    ai_redact_sensitive_data: bool = True

    # Anthropic
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    # OpenAI
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"

    # Azure OpenAI
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: Optional[str] = None
    azure_openai_api_version: str = "2024-02-15-preview"

    # Bedrock
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"

    # Local / Self-Hosted Model
    local_model_url: str = "http://localhost:11434"
    local_model_name: str = "llama3.1"
    local_model_api_key: Optional[str] = None
    local_model_timeout: int = 120

    # Data directory
    data_dir: str = DEFAULT_DATA_DIR

    # Desktop mode
    desktop: bool = True

    model_config = {
        "env_file": ENV_FILE,
        "extra": "ignore",
    }

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = os.path.join(self.data_dir, "breachwright.db")
        return f"sqlite+aiosqlite:///{db_path}"

    def ensure_data_dirs(self):
        dirs = [
            self.data_dir,
            os.path.join(self.data_dir, "uploads"),
            os.path.join(self.data_dir, "reports"),
            os.path.join(self.data_dir, "backups"),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)


settings = Settings()
settings.ensure_data_dirs()


# Configure file logging
_log_dir = os.path.join(settings.data_dir, "logs")
os.makedirs(_log_dir, exist_ok=True)
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, "breachwright.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(_file_handler)
