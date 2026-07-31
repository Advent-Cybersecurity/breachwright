from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.engagements.models import Finding, Engagement
from app.engagements.schemas import FindingCreate, FindingUpdate, FindingResponse

router = APIRouter(prefix="/api/engagements/{engagement_id}/findings", tags=["findings"])


async def _get_engagement(engagement_id: str, db: AsyncSession) -> Engagement:
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return eng


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
        .order_by(Finding.severity, Finding.cvss_score.desc())
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
        source="manual",
        created_by=current_user.id,
    )
    db.add(finding)
    await db.flush()
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

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(finding, field, value)

    await db.flush()
    return FindingResponse.model_validate(finding)


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
    await db.delete(finding)

    import os
    import shutil
    from app.config import settings
    evidence_dir = os.path.join(settings.data_dir, "evidence", finding_id)
    if os.path.isdir(evidence_dir):
        shutil.rmtree(evidence_dir, ignore_errors=True)


class BulkAction(BaseModel):
    finding_ids: list[str]
    action: str  # delete, update_severity, update_retest
    value: Optional[str] = None


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

        for f in findings:
            await db.delete(f)
            evidence_dir = os.path.join(settings.data_dir, "evidence", f.id)
            if os.path.isdir(evidence_dir):
                shutil.rmtree(evidence_dir, ignore_errors=True)
        return {"action": "delete", "count": len(findings)}

    elif body.action == "update_severity":
        if body.value not in ("critical", "high", "medium", "low", "info"):
            raise HTTPException(status_code=400, detail="Invalid severity")
        for f in findings:
            f.severity = body.value
        await db.flush()
        return {"action": "update_severity", "value": body.value, "count": len(findings)}

    elif body.action == "update_retest":
        if body.value not in ("open", "remediated", "retest_needed", "accepted_risk", None, ""):
            raise HTTPException(status_code=400, detail="Invalid retest status")
        for f in findings:
            f.retest_status = body.value or None
        await db.flush()
        return {"action": "update_retest", "value": body.value, "count": len(findings)}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
