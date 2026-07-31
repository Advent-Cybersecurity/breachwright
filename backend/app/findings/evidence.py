import os
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

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/engagements/{engagement_id}/findings/{finding_id}/evidence",
    tags=["evidence"],
)

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB


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
    await _require_finding(engagement_id, finding_id, db)

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported evidence type. Use PNG, JPEG, GIF, WebP, or PDF.",
        )

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    # Save file
    evidence_dir = os.path.join(settings.data_dir, "evidence", finding_id)
    os.makedirs(evidence_dir, exist_ok=True)

    display_name = _safe_display_name(file.filename, "evidence")
    ext = os.path.splitext(display_name)[1]
    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(evidence_dir, stored_name)

    with open(file_path, "wb") as f:
        f.write(content)

    attachment = EvidenceAttachment(
        finding_id=finding_id,
        filename=display_name,
        file_path=file_path,
        content_type=file.content_type,
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
        headers={"X-Content-Type-Options": "nosniff"},
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
        except Exception:
            pass
    await db.delete(att)
