"""Authenticated system diagnostics and backup endpoints."""

import asyncio
from contextlib import closing
import os
from pathlib import Path
import platform
import shutil
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.auth.models import User
from app.config import settings
from app.db.session import get_db
from app.engagements.models import (
    EvidenceAttachment,
    EvidenceNoteAttachment,
    Report,
    ScanUpload,
)
from app.system.backup import create_backup, sqlite_database_path, validate_backup
from app.version import APP_VERSION


router = APIRouter(prefix="/api/system", tags=["system"])
MAX_DIAGNOSTIC_FILE_RECORDS = 10000


def _sqlite_quick_check(database_path: Path) -> str:
    if not database_path.is_file():
        return "missing"
    uri = database_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as connection:
        return str(connection.execute("PRAGMA quick_check").fetchone()[0])


def _backup_metadata(path: Path) -> dict:
    manifest = validate_backup(path)
    return {
        "filename": path.name,
        "size": path.stat().st_size,
        "created_at": manifest["created_at"],
        "app_version": manifest["app_version"],
    }


async def _stored_file_diagnostics(db: AsyncSession) -> dict:
    models = (ScanUpload, EvidenceAttachment, EvidenceNoteAttachment, Report)
    total_records = 0
    checked = 0
    checked_paths = []
    remaining = MAX_DIAGNOSTIC_FILE_RECORDS
    for model in models:
        count_result = await db.execute(
            select(func.count(model.id)).where(model.file_path.is_not(None))
        )
        total_records += int(count_result.scalar_one())
        if remaining <= 0:
            continue
        paths = (await db.execute(
            select(model.file_path)
            .where(model.file_path.is_not(None))
            .order_by(model.id)
            .limit(remaining)
        )).scalars().all()
        checked += len(paths)
        checked_paths.extend(paths)
        remaining -= len(paths)
    missing = await asyncio.to_thread(
        lambda: sum(1 for path in checked_paths if not os.path.isfile(path))
    )
    return {
        "records": total_records,
        "checked": checked,
        "missing": missing,
        "complete": checked == total_records,
        "limit": MAX_DIAGNOSTIC_FILE_RECORDS,
        "status": (
            "missing_files"
            if missing
            else "ok"
            if checked == total_records
            else "partial"
        ),
    }


@router.get("/diagnostics")
async def diagnostics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data_path = Path(settings.data_dir).resolve()
    usage = shutil.disk_usage(data_path)
    database_type = (
        "sqlite"
        if settings.resolved_database_url.startswith("sqlite")
        else "postgresql"
    )
    database_exists = None
    database_size = None
    database_integrity = None
    if database_type == "sqlite":
        database_path = sqlite_database_path(settings.resolved_database_url)
        database_exists = database_path.is_file()
        database_size = database_path.stat().st_size if database_exists else 0
        try:
            database_integrity = await asyncio.to_thread(
                _sqlite_quick_check,
                database_path,
            )
        except sqlite3.Error:
            database_integrity = "error"

    backup_dir = data_path / "backups"
    return {
        "version": APP_VERSION,
        "distribution": "open_source",
        "platform": platform.system().lower(),
        "platform_release": platform.release(),
        "python_version": platform.python_version(),
        "data_directory": str(data_path),
        "data_directory_writable": os.access(data_path, os.W_OK),
        "database_type": database_type,
        "database_exists": database_exists,
        "database_size": database_size,
        "database_integrity": database_integrity,
        "stored_files": await _stored_file_diagnostics(db),
        "free_space": usage.free,
        "backup_count": len(list(backup_dir.glob("breachwright-backup-*.zip"))),
    }


@router.get("/backups")
async def list_backups(admin: User = Depends(require_admin)):
    backup_dir = Path(settings.data_dir) / "backups"
    backups = sorted(
        backup_dir.glob("breachwright-backup-*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    valid_backups = []
    for path in backups:
        try:
            valid_backups.append(_backup_metadata(path))
        except (OSError, ValueError, KeyError):
            continue
    return valid_backups


@router.post("/backups", status_code=201)
async def make_backup(admin: User = Depends(require_admin)):
    try:
        backup_path = await asyncio.to_thread(
            create_backup,
            settings.data_dir,
            settings.resolved_database_url,
            APP_VERSION,
        )
        return _backup_metadata(backup_path)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/backups/{filename}")
async def download_backup(
    filename: str,
    admin: User = Depends(require_admin),
):
    if Path(filename).name != filename or not filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    backup_path = (Path(settings.data_dir) / "backups" / filename).resolve()
    expected_parent = (Path(settings.data_dir) / "backups").resolve()
    if backup_path.parent != expected_parent or not backup_path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        validate_backup(backup_path)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=f"Backup is invalid: {exc}") from exc
    return FileResponse(
        backup_path,
        filename=filename,
        media_type="application/zip",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/backups/{filename}", status_code=204)
async def delete_backup(
    filename: str,
    admin: User = Depends(require_admin),
):
    if (
        Path(filename).name != filename
        or not filename.startswith("breachwright-backup-")
        or not filename.endswith(".zip")
    ):
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    backup_path = (Path(settings.data_dir) / "backups" / filename).resolve()
    expected_parent = (Path(settings.data_dir) / "backups").resolve()
    if backup_path.parent != expected_parent or not backup_path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        backup_path.unlink()
    except OSError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Backup could not be deleted: {exc}",
        ) from exc
