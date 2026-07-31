"""Engagement evidence notebook for notes and pre-finding attachments."""

import os
import shutil
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.config import settings
from app.db.session import get_db
from app.engagements.models import (
    Engagement,
    EvidenceNote,
    EvidenceNoteAttachment,
    Finding,
)
from app.findings.evidence import (
    ALLOWED_TYPES,
    CANONICAL_EXTENSIONS,
    MAX_SIZE,
    _matches_declared_type,
    _resolved_content_type,
    _safe_display_name,
)
from app.engagements.schemas import FindingCreate, FindingResponse
from app.findings.history import record_history, snapshot as finding_snapshot


router = APIRouter(prefix="/api/engagements/{engagement_id}/notebook", tags=["evidence_notebook"])


class EvidenceNoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: Optional[str] = Field(default=None, max_length=200000)
    asset: Optional[str] = Field(default=None, max_length=500)
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(default_factory=list, max_length=20)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}

    @field_validator("tags")
    @classmethod
    def tags_are_unique(cls, value):
        normalized = [tag.casefold() for tag in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Tags must be unique")
        return value


async def _require_engagement(db: AsyncSession, engagement_id: str) -> None:
    exists = (await db.execute(
        select(Engagement.id).where(Engagement.id == engagement_id)
    )).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Engagement not found")


async def _require_note(db: AsyncSession, engagement_id: str, note_id: str) -> EvidenceNote:
    note = (await db.execute(
        select(EvidenceNote).where(
            EvidenceNote.id == note_id,
            EvidenceNote.engagement_id == engagement_id,
        )
    )).scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Evidence note not found")
    return note


async def _linked_finding_id(db: AsyncSession, engagement_id: str, note_id: str) -> str | None:
    findings = (await db.execute(
        select(Finding.id, Finding.evidence_refs).where(Finding.engagement_id == engagement_id)
    )).all()
    return next((
        finding_id
        for finding_id, refs in findings
        if any(
            isinstance(ref, dict) and ref.get("evidence_note_id") == note_id
            for ref in (refs or [])
        )
    ), None)


async def _require_unlinked_note(db: AsyncSession, engagement_id: str, note_id: str) -> None:
    if await _linked_finding_id(db, engagement_id, note_id):
        raise HTTPException(
            status_code=409,
            detail="This note is linked to a finding and is locked to preserve its evidence provenance",
        )


def attachment_response(engagement_id: str, note_id: str, attachment: EvidenceNoteAttachment) -> dict:
    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "file_size": attachment.file_size,
        "created_at": attachment.created_at,
        "url": f"/api/engagements/{engagement_id}/notebook/{note_id}/attachments/{attachment.id}/file",
    }


def note_response(note: EvidenceNote, attachments: list[dict], finding_id: str | None = None) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "body": note.body,
        "asset": note.asset,
        "tags": note.tags or [],
        "source_type": note.source_type,
        "source_id": note.source_id,
        "attachments": attachments,
        "finding_id": finding_id,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


@router.get("")
async def list_notes(
    engagement_id: str,
    limit: int = Query(default=500, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_engagement(db, engagement_id)
    total = (await db.execute(
        select(func.count(EvidenceNote.id)).where(EvidenceNote.engagement_id == engagement_id)
    )).scalar_one()
    notes = list((await db.execute(
        select(EvidenceNote)
        .where(EvidenceNote.engagement_id == engagement_id)
        .order_by(EvidenceNote.updated_at.desc(), EvidenceNote.id)
        .limit(limit)
    )).scalars().all())
    note_ids = [note.id for note in notes]
    attachments_by_note: dict[str, list[dict]] = {note_id: [] for note_id in note_ids}
    if note_ids:
        attachments = list((await db.execute(
            select(EvidenceNoteAttachment)
            .where(EvidenceNoteAttachment.note_id.in_(note_ids))
            .order_by(EvidenceNoteAttachment.created_at.desc(), EvidenceNoteAttachment.id)
        )).scalars().all())
        for attachment in attachments:
            attachments_by_note[attachment.note_id].append(
                attachment_response(engagement_id, attachment.note_id, attachment)
            )
    linked_findings = list((await db.execute(
        select(Finding.id, Finding.evidence_refs).where(Finding.engagement_id == engagement_id)
    )).all())
    finding_by_note = {
        ref.get("evidence_note_id"): finding_id
        for finding_id, refs in linked_findings
        for ref in (refs or [])
        if isinstance(ref, dict) and ref.get("evidence_note_id")
    }
    return {
        "notes": [note_response(note, attachments_by_note[note.id], finding_by_note.get(note.id)) for note in notes],
        "total": total,
        "truncated": total > len(notes),
    }


@router.post("", status_code=201)
async def create_note(
    engagement_id: str,
    body: EvidenceNoteInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    await _require_engagement(db, engagement_id)
    note = EvidenceNote(
        engagement_id=engagement_id,
        title=body.title,
        body=body.body,
        asset=body.asset,
        tags=body.tags,
        source_type="manual",
        source_id=None,
        created_by=current_user.id,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return note_response(note, [])


@router.put("/{note_id}")
async def update_note(
    engagement_id: str,
    note_id: str,
    body: EvidenceNoteInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    note = await _require_note(db, engagement_id, note_id)
    await _require_unlinked_note(db, engagement_id, note_id)
    note.title = body.title
    note.body = body.body
    note.asset = body.asset
    note.tags = body.tags
    await db.flush()
    await db.refresh(note)
    attachments = list((await db.execute(
        select(EvidenceNoteAttachment)
        .where(EvidenceNoteAttachment.note_id == note_id)
        .order_by(EvidenceNoteAttachment.created_at.desc(), EvidenceNoteAttachment.id)
    )).scalars().all())
    return note_response(
        note,
        [attachment_response(engagement_id, note_id, attachment) for attachment in attachments],
        None,
    )


@router.post("/{note_id}/finding", response_model=FindingResponse, status_code=201)
async def promote_note_to_finding(
    engagement_id: str,
    note_id: str,
    body: FindingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    note = await _require_note(db, engagement_id, note_id)
    if await _linked_finding_id(db, engagement_id, note_id):
        raise HTTPException(status_code=409, detail="This evidence note is already linked to a finding")
    attachments = list((await db.execute(
        select(EvidenceNoteAttachment)
        .where(EvidenceNoteAttachment.note_id == note_id)
        .order_by(EvidenceNoteAttachment.created_at, EvidenceNoteAttachment.id)
    )).scalars().all())
    evidence_ref = {
        "id": f"NOTE-{note.id[:8].upper()}",
        "evidence_note_id": note.id,
        "title": note.title,
        "asset": note.asset,
        "tags": note.tags or [],
        "attachment_ids": [attachment.id for attachment in attachments],
        "attachment_filenames": [attachment.filename for attachment in attachments],
        "excerpt": (note.body or "")[:2000],
    }
    finding = Finding(
        engagement_id=engagement_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        cvss_score=body.cvss_score,
        affected_hosts=body.affected_hosts,
        evidence=body.evidence,
        remediation=body.remediation,
        retest_status=body.retest_status,
        retest_due_date=body.retest_due_date,
        source="notebook_reviewed",
        evidence_refs=[evidence_ref],
        ai_inference=False,
        created_by=current_user.id,
    )
    db.add(finding)
    await db.flush()
    await record_history(
        db,
        finding,
        action="notebook_note_accepted",
        created_by=current_user.id,
        source="notebook_reviewed",
        changes={
            field: {"from": None, "to": value}
            for field, value in finding_snapshot(finding).items()
            if value is not None
        },
    )
    return FindingResponse.model_validate(finding)


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    engagement_id: str,
    note_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    note = await _require_note(db, engagement_id, note_id)
    await _require_unlinked_note(db, engagement_id, note_id)
    await db.execute(delete(EvidenceNoteAttachment).where(EvidenceNoteAttachment.note_id == note_id))
    await db.delete(note)
    note_dir = os.path.join(settings.data_dir, "notebook", engagement_id, note_id)
    if os.path.isdir(note_dir):
        shutil.rmtree(note_dir, ignore_errors=True)


@router.post("/{note_id}/attachments")
async def upload_attachment(
    engagement_id: str,
    note_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    await _require_note(db, engagement_id, note_id)
    await _require_unlinked_note(db, engagement_id, note_id)
    content_type = _resolved_content_type(file.filename, file.content_type)
    if not content_type:
        supported = ", ".join(sorted(ALLOWED_TYPES))
        raise HTTPException(status_code=415, detail=f"Unsupported evidence type. Supported media types: {supported}")
    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    if not _matches_declared_type(content_type, content):
        raise HTTPException(status_code=415, detail="Evidence content does not match its declared file type")

    note_dir = os.path.join(settings.data_dir, "notebook", engagement_id, note_id)
    os.makedirs(note_dir, exist_ok=True)
    display_name = _safe_display_name(file.filename, "evidence")
    file_path = os.path.join(note_dir, f"{uuid.uuid4().hex}{CANONICAL_EXTENSIONS[content_type]}")
    with open(file_path, "wb") as stored:
        stored.write(content)
    attachment = EvidenceNoteAttachment(
        note_id=note_id,
        filename=display_name,
        file_path=file_path,
        content_type=content_type,
        file_size=len(content),
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    await db.flush()
    await db.refresh(attachment)
    return attachment_response(engagement_id, note_id, attachment)


@router.get("/{note_id}/attachments/{attachment_id}/file")
async def download_attachment(
    engagement_id: str,
    note_id: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_note(db, engagement_id, note_id)
    attachment = (await db.execute(
        select(EvidenceNoteAttachment).where(
            EvidenceNoteAttachment.id == attachment_id,
            EvidenceNoteAttachment.note_id == note_id,
        )
    )).scalar_one_or_none()
    if not attachment or not os.path.isfile(attachment.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        attachment.file_path,
        filename=attachment.filename,
        media_type=attachment.content_type or "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.delete("/{note_id}/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    engagement_id: str,
    note_id: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    await _require_note(db, engagement_id, note_id)
    await _require_unlinked_note(db, engagement_id, note_id)
    attachment = (await db.execute(
        select(EvidenceNoteAttachment).where(
            EvidenceNoteAttachment.id == attachment_id,
            EvidenceNoteAttachment.note_id == note_id,
        )
    )).scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if attachment.file_path and os.path.isfile(attachment.file_path):
        try:
            os.remove(attachment.file_path)
        except OSError:
            pass
    await db.delete(attachment)
