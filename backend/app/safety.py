"""Small security boundaries shared by local file and logging workflows."""

from pathlib import Path
import uuid


LOG_CONTROL_CHARACTERS = str.maketrans(
    {
        "\r": " ",
        "\n": " ",
        "\x00": " ",
        "\x85": " ",
        "\u2028": " ",
        "\u2029": " ",
    }
)


def canonical_uuid(value: str) -> str:
    """Return one canonical UUID path component or reject the value."""
    return str(uuid.UUID(str(value)))


def app_data_directory(data_dir: str, category: str, *record_ids: str) -> Path:
    """Build a canonical app-owned directory below one fixed data category."""
    data_root = Path(data_dir).resolve()
    category_root = (data_root / category).resolve()
    category_root.relative_to(data_root)
    candidate = category_root.joinpath(
        *(canonical_uuid(record_id) for record_id in record_ids)
    ).resolve()
    candidate.relative_to(category_root)
    return candidate


def safe_log_value(value: object, max_length: int = 500) -> str:
    """Bound a value and flatten characters that can forge a log record."""
    text = str(value).translate(LOG_CONTROL_CHARACTERS)
    text = "".join(character if ord(character) >= 32 else " " for character in text)
    return text[:max_length]
