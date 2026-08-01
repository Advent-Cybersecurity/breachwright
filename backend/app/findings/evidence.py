import os
import json
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.engagements.models import Finding, EvidenceAttachment
from app.config import settings
from app.safety import app_data_directory

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/engagements/{engagement_id}/findings/{finding_id}/evidence",
    tags=["evidence"],
)

ALLOWED_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/har+json",
}
CANONICAL_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/har+json": ".har",
}
TEXT_EXTENSION_TYPES = {
    ".txt": "text/plain",
    ".http": "text/plain",
    ".req": "text/plain",
    ".resp": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".har": "application/har+json",
}
MAX_SIZE = 10 * 1024 * 1024  # 10MB


def _matches_declared_type(content_type: str, content: bytes) -> bool:
    signatures = {
        "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
        "image/gif": lambda data: data.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": lambda data: (
            len(data) >= 12
            and data.startswith(b"RIFF")
            and data[8:12] == b"WEBP"
        ),
        "application/pdf": lambda data: data.startswith(b"%PDF-"),
    }
    if content_type in signatures:
        return signatures[content_type](content)
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if "\x00" in decoded:
        return False
    if content_type in {"application/json", "application/har+json"}:
        try:
            parsed = json.loads(decoded)
        except (json.JSONDecodeError, RecursionError):
            return False
        return isinstance(parsed, (dict, list))
    return True


def _resolved_content_type(filename: str | None, declared: str | None) -> str | None:
    if declared in ALLOWED_TYPES:
        return declared
    extension = os.path.splitext(filename or "")[1].lower()
    if declared in {None, "", "application/octet-stream"}:
        return TEXT_EXTENSION_TYPES.get(extension)
    return None


def _safe_display_name(filename: str | None, fallback: str) -> str:
    name = (filename or fallback).replace("\\", "/").rsplit("/", 1)[-1]
    return name if name not in {"", ".", ".."} else fallback


async def _require_finding(
    engagement_id: str,
    finding_id: str,
    db: AsyncSession,
) -> Finding:
    result = await db.execute(
        select(Finding).where(
            Finding.id == finding_id,
            Finding.engagement_id == engagement_id,
        )
    )
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


@router.get("")
async def list_evidence(
    engagement_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_finding(engagement_id, finding_id, db)
    result = await db.execute(
        select(EvidenceAttachment)
        .where(EvidenceAttachment.finding_id == finding_id)
        .order_by(EvidenceAttachment.created_at.desc())
    )
    attachments = result.scalars().all()
    return [
        {
            "id": a.id,
            "filename": a.filename,
            "content_type": a.content_type,
            "file_size": a.file_size,
            "url": (
                f"/api/engagements/{engagement_id}/findings/"
                f"{finding_id}/evidence/{a.id}/file"
            ),
        }
        for a in attachments
    ]


@router.post("")
async def upload_evidence(
    engagement_id: str,
    finding_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    # Verify finding exists
    finding = await _require_finding(engagement_id, finding_id, db)

    content_type = _resolved_content_type(file.filename, file.content_type)
    if not content_type:
        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported evidence type. Use PNG, JPEG, GIF, WebP, PDF, "
                "plain text, Markdown, CSV, JSON, or HAR."
            ),
        )

    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    if not _matches_declared_type(content_type, content):
        raise HTTPException(
            status_code=415,
            detail="Evidence content does not match its declared file type",
        )

    # Save file
    evidence_dir = app_data_directory(settings.data_dir, "evidence", finding.id)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    display_name = _safe_display_name(file.filename, "evidence")
    stored_name = (
        f"{uuid.uuid4().hex}{CANONICAL_EXTENSIONS[content_type]}"
    )
    file_path = evidence_dir / stored_name

    with file_path.open("wb") as f:
        f.write(content)

    attachment = EvidenceAttachment(
        finding_id=finding_id,
        filename=display_name,
        file_path=str(file_path),
        content_type=content_type,
        file_size=len(content),
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    await db.flush()

    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "file_size": attachment.file_size,
        "url": (
            f"/api/engagements/{engagement_id}/findings/"
            f"{finding_id}/evidence/{attachment.id}/file"
        ),
    }


@router.get("/{attachment_id}/file")
async def download_evidence(
    engagement_id: str,
    finding_id: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_finding(engagement_id, finding_id, db)

    result = await db.execute(
        select(EvidenceAttachment).where(
            EvidenceAttachment.id == attachment_id,
            EvidenceAttachment.finding_id == finding_id,
        )
    )
    att = result.scalar_one_or_none()
    if not att or not att.file_path or not os.path.exists(att.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        att.file_path,
        filename=att.filename,
        media_type=att.content_type or "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.delete("/{attachment_id}", status_code=204)
async def delete_evidence(
    engagement_id: str,
    finding_id: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    await _require_finding(engagement_id, finding_id, db)
    result = await db.execute(
        select(EvidenceAttachment).where(
            EvidenceAttachment.id == attachment_id,
            EvidenceAttachment.finding_id == finding_id,
        )
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if att.file_path and os.path.exists(att.file_path):
        try:
            os.remove(att.file_path)
        except OSError as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Evidence file could not be removed. Review file "
                    "permissions and retry."
                ),
            ) from exc
    await db.delete(att)
