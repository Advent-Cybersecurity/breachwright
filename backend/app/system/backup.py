"""Portable, local-only backup and restore support for SQLite installations."""

from datetime import datetime, timezone
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import uuid
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy.engine import make_url


BACKUP_FORMAT_VERSION = 1
DATA_FOLDERS = ("evidence", "uploads", "reports")
MAX_BACKUP_ENTRIES = 10000
MAX_BACKUP_MEMBER_SIZE = 2 * 1024 * 1024 * 1024
MAX_BACKUP_TOTAL_SIZE = 10 * 1024 * 1024 * 1024
MAX_BACKUP_COMPRESSION_RATIO = 1000
MAX_MANIFEST_SIZE = 5 * 1024 * 1024


@contextmanager
def _staging_directory(parent: Path, prefix: str):
    """Create an app-owned staging folder that works in packaged Windows builds."""
    stage = parent / f"{prefix}{uuid.uuid4().hex}"
    stage.mkdir(parents=False, exist_ok=False)
    try:
        yield stage
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def sqlite_database_path(database_url: str) -> Path:
    """Resolve the SQLite file from a SQLAlchemy URL."""
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        raise ValueError("Built-in backups currently support SQLite installations only")
    if not url.database or url.database == ":memory:":
        raise ValueError("A file-backed SQLite database is required")
    path = Path(url.database)
    return path if path.is_absolute() else Path.cwd() / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_sqlite_database(source_path: Path, destination_path: Path) -> None:
    if not source_path.is_file():
        raise FileNotFoundError(f"Database file not found: {source_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source_path)) as source:
        with closing(sqlite3.connect(destination_path)) as destination:
            source.backup(destination)


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _copy_data_folder(source: Path, destination: Path) -> list[Path]:
    """Copy regular files without following links outside the data directory."""
    copied: list[Path] = []
    if _is_link_like(source):
        return copied
    destination.mkdir(parents=True, exist_ok=True)
    for current_root, directory_names, file_names in os.walk(
        source,
        followlinks=False,
    ):
        current = Path(current_root)
        directory_names[:] = [
            name
            for name in directory_names
            if not _is_link_like(current / name)
        ]
        relative = current.relative_to(source)
        target_root = destination / relative
        target_root.mkdir(parents=True, exist_ok=True)
        for file_name in file_names:
            source_file = current / file_name
            if _is_link_like(source_file) or not source_file.is_file():
                continue
            destination_file = target_root / file_name
            shutil.copy2(source_file, destination_file)
            copied.append(destination_file)
    return copied


def create_backup(data_dir: str, database_url: str, app_version: str) -> Path:
    """Create a verified ZIP backup without including API keys or signing secrets."""
    data_path = Path(data_dir).resolve()
    backup_dir = data_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    final_path = backup_dir / f"breachwright-backup-{timestamp}.zip"

    counter = 1
    while final_path.exists():
        final_path = backup_dir / f"breachwright-backup-{timestamp}-{counter}.zip"
        counter += 1

    with _staging_directory(backup_dir, ".backup-") as stage:
        database_copy = stage / "database" / "breachwright.db"
        _copy_sqlite_database(
            sqlite_database_path(database_url).resolve(),
            database_copy,
        )

        copied_files = [database_copy]
        for folder_name in DATA_FOLDERS:
            source_folder = data_path / folder_name
            if not source_folder.is_dir():
                continue
            destination_folder = stage / "data" / folder_name
            copied_files.extend(
                _copy_data_folder(source_folder, destination_folder)
            )

        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "app_version": app_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": "database/breachwright.db",
            "data_folders": list(DATA_FOLDERS),
            "excluded_secrets": [".env", ".secret_key"],
            "files": {
                path.relative_to(stage).as_posix(): {
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                for path in copied_files
            },
        }
        manifest_path = stage / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        temporary_archive = stage / "backup.zip"
        with ZipFile(temporary_archive, "w", compression=ZIP_DEFLATED) as archive:
            archive.write(manifest_path, "manifest.json")
            for path in copied_files:
                archive.write(path, path.relative_to(stage).as_posix())

        shutil.copy2(temporary_archive, final_path)

    validate_backup(final_path)
    return final_path


def _safe_members(archive: ZipFile) -> list[str]:
    entries = archive.infolist()
    if len(entries) > MAX_BACKUP_ENTRIES:
        raise ValueError("Backup contains too many files")

    members: list[str] = []
    seen: set[str] = set()
    total_size = 0
    for entry in entries:
        normalized = entry.filename.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or ":" in path.parts[0]
        ):
            raise ValueError(f"Unsafe backup path: {entry.filename}")
        if normalized in seen:
            raise ValueError(f"Duplicate backup path: {entry.filename}")
        seen.add(normalized)
        if entry.file_size > MAX_BACKUP_MEMBER_SIZE:
            raise ValueError(f"Backup file is too large: {entry.filename}")
        total_size += entry.file_size
        if total_size > MAX_BACKUP_TOTAL_SIZE:
            raise ValueError("Backup expands beyond the supported size")
        if (
            entry.file_size > 1024 * 1024
            and entry.compress_size > 0
            and entry.file_size / entry.compress_size > MAX_BACKUP_COMPRESSION_RATIO
        ):
            raise ValueError(
                f"Unsafe backup compression ratio: {entry.filename}"
            )
        members.append(normalized)
    return members


def validate_backup(backup_path: Path) -> dict:
    """Validate archive structure, version, sizes, and SHA-256 checksums."""
    with ZipFile(backup_path, "r") as archive:
        members = _safe_members(archive)
        if "manifest.json" not in members:
            raise ValueError("Backup manifest is missing")
        if archive.getinfo("manifest.json").file_size > MAX_MANIFEST_SIZE:
            raise ValueError("Backup manifest is too large")
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Backup manifest is invalid") from exc
        if not isinstance(manifest, dict) or not isinstance(
            manifest.get("files"),
            dict,
        ):
            raise ValueError("Backup manifest structure is invalid")
        if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
            raise ValueError("Unsupported backup format version")
        for name, expected in manifest.get("files", {}).items():
            if (
                not isinstance(name, str)
                or not isinstance(expected, dict)
                or not isinstance(expected.get("size"), int)
                or not isinstance(expected.get("sha256"), str)
            ):
                raise ValueError("Backup manifest file metadata is invalid")
            if name not in members:
                raise ValueError(f"Backup file is missing: {name}")
            info = archive.getinfo(name)
            if info.file_size != expected["size"]:
                raise ValueError(f"Backup file size mismatch: {name}")
            digest = hashlib.sha256()
            with archive.open(name) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected["sha256"]:
                raise ValueError(f"Backup checksum mismatch: {name}")
        if manifest.get("database") not in members:
            raise ValueError("Backup database is missing")
        return manifest


def restore_backup(
    backup_path: Path,
    data_dir: str,
    database_url: str,
) -> Path:
    """Restore a validated backup and preserve displaced data in a safety folder.

    Breachwright must be stopped before this function is called.
    """
    backup_path = backup_path.resolve()
    manifest = validate_backup(backup_path)
    data_path = Path(data_dir).resolve()
    data_path.mkdir(parents=True, exist_ok=True)
    safety_path = data_path / (
        "restore-safety-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    )
    safety_path.mkdir(parents=True, exist_ok=False)

    with _staging_directory(data_path, ".restore-") as stage:
        with ZipFile(backup_path, "r") as archive:
            _safe_members(archive)
            archive.extractall(stage)

        database_path = sqlite_database_path(database_url).resolve()
        restored_database = stage / manifest["database"]
        with closing(sqlite3.connect(restored_database)) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Restored database failed integrity check: {integrity}")

        database_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_database = database_path.with_name(
            f".{database_path.name}.restore-{uuid.uuid4().hex}"
        )
        shutil.copy2(restored_database, candidate_database)

        displaced: list[tuple[Path, Path]] = []
        installed: list[Path] = []
        try:
            if database_path.exists():
                safety_database = safety_path / "database" / database_path.name
                safety_database.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(database_path), safety_database)
                displaced.append((database_path, safety_database))
            os.replace(candidate_database, database_path)
            installed.append(database_path)

            for folder_name in DATA_FOLDERS:
                current = data_path / folder_name
                restored = stage / "data" / folder_name
                if current.exists():
                    safety_folder = safety_path / folder_name
                    shutil.move(str(current), safety_folder)
                    displaced.append((current, safety_folder))
                if restored.exists():
                    shutil.move(str(restored), current)
                else:
                    current.mkdir(parents=True, exist_ok=True)
                installed.append(current)
        except Exception:
            for current in reversed(installed):
                if current.is_dir():
                    shutil.rmtree(current, ignore_errors=True)
                elif current.exists():
                    current.unlink()
            for original, safety_copy in reversed(displaced):
                if safety_copy.exists():
                    original.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(safety_copy), original)
            raise
        finally:
            if candidate_database.exists():
                candidate_database.unlink()

    return safety_path
