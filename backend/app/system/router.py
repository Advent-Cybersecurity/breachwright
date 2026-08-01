"""Authenticated system diagnostics and backup endpoints."""

import asyncio
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import shutil
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
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
        "file_count": len(manifest["files"]),
        "valid": True,
    }


def _stored_backup_path(filename: str) -> Path | None:
    """Resolve a requested backup only from app-enumerated stored archives."""
    if Path(filename).name != filename or not filename.endswith(".zip"):
        return None
    backup_root = (Path(settings.data_dir) / "backups").resolve()
    for candidate in backup_root.glob("breachwright-backup-*.zip"):
        if candidate.name != filename or candidate.is_symlink():
            continue
        resolved = candidate.resolve()
        if resolved.parent == backup_root and resolved.is_file():
            return resolved
    return None


def _list_backup_metadata(backup_dir: Path) -> list[dict]:
    """Verify stored backups without blocking the application's request loop."""
    def modified_time(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0

    paths = list(backup_dir.glob("breachwright-backup-*.zip"))
    paths.sort(key=modified_time, reverse=True)
    results: list[dict] = []
    for path in paths:
        try:
            results.append(_backup_metadata(path))
        except (OSError, ValueError, KeyError) as exc:
            try:
                stat = path.stat()
            except OSError:
                continue
            results.append(
                {
                    "filename": path.name,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(
                        stat.st_mtime,
                        timezone.utc,
                    ).isoformat(),
                    "app_version": None,
                    "file_count": None,
                    "valid": False,
                    "error": str(exc),
                }
            )
    return results


def _create_backup_metadata() -> dict:
    path = create_backup(
        settings.data_dir,
        settings.resolved_database_url,
        APP_VERSION,
    )
    return _backup_metadata(path)


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


async def _diagnostics_payload(db: AsyncSession) -> dict:
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


def _support_ai_summary() -> dict:
    provider = settings.ai_provider.lower()
    if provider in {"ollama", "vllm", "llamacpp", "lmstudio"}:
        provider = "local"
    configured = {
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
        "azure": bool(settings.azure_openai_api_key),
        "local": bool(settings.local_model_api_key),
        "bedrock": None,
    }.get(provider)
    return {
        "provider": provider,
        "credential_configured": configured,
        "sensitive_data_redaction": settings.ai_redact_sensitive_data,
    }


@router.get("/diagnostics")
async def diagnostics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _diagnostics_payload(db)


@router.get("/support-snapshot")
async def support_snapshot(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download bounded troubleshooting metadata without workspace content."""
    diagnostic_data = await _diagnostics_payload(db)
    diagnostic_data.pop("data_directory", None)
    created_at = datetime.now(timezone.utc)
    filename = created_at.strftime("breachwright-support-%Y%m%d-%H%M%S.json")
    return JSONResponse(
        {
            "schema_version": 1,
            "generated_at": created_at.isoformat(),
            "diagnostics": diagnostic_data,
            "ai": _support_ai_summary(),
            "privacy": {
                "contains_logs": False,
                "contains_credentials": False,
                "contains_workspace_content": False,
                "contains_data_path": False,
            },
        },
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/backups")
async def list_backups(admin: User = Depends(require_admin)):
    backup_dir = Path(settings.data_dir) / "backups"
    return await asyncio.to_thread(_list_backup_metadata, backup_dir)


@router.post("/backups", status_code=201)
async def make_backup(admin: User = Depends(require_admin)):
    try:
        return await asyncio.to_thread(_create_backup_metadata)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/backups/{filename}")
async def download_backup(
    filename: str,
    admin: User = Depends(require_admin),
):
    backup_path = _stored_backup_path(filename)
    if backup_path is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        await asyncio.to_thread(validate_backup, backup_path)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=f"Backup is invalid: {exc}") from exc
    return FileResponse(
        backup_path,
        filename=backup_path.name,
        media_type="application/zip",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/backups/{filename}", status_code=204)
async def delete_backup(
    filename: str,
    admin: User = Depends(require_admin),
):
    backup_path = _stored_backup_path(filename)
    if backup_path is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        backup_path.unlink()
    except OSError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Backup could not be deleted: {exc}",
        ) from exc
