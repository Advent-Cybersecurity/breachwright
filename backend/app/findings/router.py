from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Annotated, Optional
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.engagements.models import Finding, FindingHistory, Engagement
from app.engagements.schemas import FindingCreate, FindingUpdate, FindingResponse
from app.findings.history import diff, record_history, snapshot
from app.config import settings
from app.safety import app_data_directory

router = APIRouter(prefix="/api/engagements/{engagement_id}/findings", tags=["findings"])


async def _get_engagement(engagement_id: str, db: AsyncSession) -> Engagement:
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return eng


class DuplicateCheck(BaseModel):
    title: str = Field(min_length=2, max_length=500)
    affected_hosts: Optional[str] = Field(default=None, max_length=50000)

    model_config = {"str_strip_whitespace": True}


def _host_tokens(value: str | None) -> set[str]:
    return {
        token.strip().lower()
        for token in str(value or "").replace("\r", "\n").replace(",", "\n").split("\n")
        if token.strip()
    }


@router.post("/duplicate-check")
async def duplicate_check(
    engagement_id: str,
    body: DuplicateCheck,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Warn about exact normalized titles without preventing valid repeats."""
    await _get_engagement(engagement_id, db)
    normalized_title = body.title.strip().lower()
    result = await db.execute(
        select(Finding)
        .where(
            Finding.engagement_id == engagement_id,
            func.lower(func.trim(Finding.title)) == normalized_title,
        )
        .order_by(Finding.created_at, Finding.id)
        .limit(20)
    )
    requested_hosts = _host_tokens(body.affected_hosts)
    matches = []
    for finding in result.scalars().all():
        existing_hosts = _host_tokens(finding.affected_hosts)
        matches.append({
            "id": finding.id,
            "title": finding.title,
            "severity": finding.severity,
            "affected_hosts": finding.affected_hosts,
            "host_overlap": bool(requested_hosts & existing_hosts),
        })
    return {"count": len(matches), "matches": matches}


@router.get("", response_model=list[FindingResponse])
async def list_findings(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_engagement(engagement_id, db)
    result = await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .order_by(
            case(
                (Finding.severity == "critical", 0),
                (Finding.severity == "high", 1),
                (Finding.severity == "medium", 2),
                (Finding.severity == "low", 3),
                else_=4,
            ),
            Finding.cvss_score.desc(),
            Finding.created_at,
            Finding.id,
        )
    )
    return [FindingResponse.model_validate(f) for f in result.scalars().all()]


@router.post("", response_model=FindingResponse, status_code=201)
async def create_finding(
    engagement_id: str,
    request: FindingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    await _get_engagement(engagement_id, db)
    finding = Finding(
        engagement_id=engagement_id,
        title=request.title,
        description=request.description,
        severity=request.severity,
        cvss_score=request.cvss_score,
        affected_hosts=request.affected_hosts,
        evidence=request.evidence,
        remediation=request.remediation,
        retest_status=request.retest_status,
        retest_due_date=request.retest_due_date,
        source="manual",
        created_by=current_user.id,
    )
    db.add(finding)
    await db.flush()
    await record_history(
        db,
        finding,
        action="created",
        created_by=current_user.id,
        changes={field: {"from": None, "to": value} for field, value in snapshot(finding).items() if value is not None},
    )
    return FindingResponse.model_validate(finding)


@router.put("/{finding_id}", response_model=FindingResponse)
async def update_finding(
    engagement_id: str,
    finding_id: str,
    request: FindingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(
        select(Finding).where(Finding.id == finding_id, Finding.engagement_id == engagement_id)
    )
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    before = snapshot(finding)
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(finding, field, value)

    await db.flush()
    await record_history(
        db,
        finding,
        action="updated",
        created_by=current_user.id,
        changes=diff(before, snapshot(finding)),
    )
    return FindingResponse.model_validate(finding)


@router.get("/{finding_id}/history")
async def get_finding_history(
    engagement_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    finding = await db.execute(
        select(Finding.id).where(Finding.id == finding_id, Finding.engagement_id == engagement_id)
    )
    if not finding.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Finding not found")
    result = await db.execute(
        select(FindingHistory)
        .where(FindingHistory.finding_id == finding_id)
        .order_by(FindingHistory.created_at.desc(), FindingHistory.id.desc())
    )
    return [
        {
            "id": entry.id,
            "action": entry.action,
            "changes": entry.changes,
            "source": entry.source,
            "created_at": entry.created_at,
        }
        for entry in result.scalars().all()
    ]


@router.get("/{finding_id}", response_model=FindingResponse)
async def get_finding(
    engagement_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Finding).where(Finding.id == finding_id, Finding.engagement_id == engagement_id)
    )
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return FindingResponse.model_validate(finding)


@router.delete("/{finding_id}", status_code=204)
async def delete_finding(
    engagement_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(
        select(Finding).where(Finding.id == finding_id, Finding.engagement_id == engagement_id)
    )
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    from sqlalchemy import delete
    from app.engagements.models import EvidenceAttachment
    await db.execute(
        delete(EvidenceAttachment).where(
            EvidenceAttachment.finding_id == finding_id
        )
    )
    await db.execute(
        delete(FindingHistory).where(FindingHistory.finding_id == finding_id)
    )
    await db.delete(finding)

    import shutil
    evidence_dir = app_data_directory(settings.data_dir, "evidence", finding.id)
    if evidence_dir.is_dir():
        shutil.rmtree(evidence_dir, ignore_errors=True)


class BulkAction(BaseModel):
    finding_ids: list[
        Annotated[str, Field(min_length=1, max_length=36)]
    ] = Field(min_length=1, max_length=1000)
    action: str = Field(min_length=1, max_length=50)
    value: Optional[str] = Field(default=None, max_length=50)


@router.post("/bulk")
async def bulk_action(
    engagement_id: str,
    body: BulkAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    if not body.finding_ids:
        raise HTTPException(status_code=400, detail="No findings selected")

    result = await db.execute(
        select(Finding).where(
            Finding.id.in_(body.finding_ids),
            Finding.engagement_id == engagement_id,
        )
    )
    findings = result.scalars().all()

    if body.action == "delete":
        import os
        import shutil
        from app.config import settings
        from app.engagements.models import EvidenceAttachment
        from sqlalchemy import delete

        for f in findings:
            await db.execute(
                delete(EvidenceAttachment).where(
                    EvidenceAttachment.finding_id == f.id
                )
            )
            await db.execute(
                delete(FindingHistory).where(FindingHistory.finding_id == f.id)
            )
            await db.delete(f)
            evidence_dir = os.path.join(settings.data_dir, "evidence", f.id)
            if os.path.isdir(evidence_dir):
                shutil.rmtree(evidence_dir, ignore_errors=True)
        return {"action": "delete", "count": len(findings)}

    elif body.action == "update_severity":
        if body.value not in ("critical", "high", "medium", "low", "info"):
            raise HTTPException(status_code=400, detail="Invalid severity")
        for f in findings:
            before = snapshot(f)
            f.severity = body.value
            await db.flush()
            await record_history(db, f, action="bulk_updated", created_by=current_user.id, changes=diff(before, snapshot(f)))
        await db.flush()
        return {"action": "update_severity", "value": body.value, "count": len(findings)}

    elif body.action == "update_retest":
        if body.value not in ("open", "remediated", "retest_needed", "accepted_risk", None, ""):
            raise HTTPException(status_code=400, detail="Invalid retest status")
        for f in findings:
            before = snapshot(f)
            f.retest_status = body.value or None
            await db.flush()
            await record_history(db, f, action="bulk_updated", created_by=current_user.id, changes=diff(before, snapshot(f)))
        await db.flush()
        return {"action": "update_retest", "value": body.value, "count": len(findings)}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
