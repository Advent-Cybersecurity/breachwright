from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.engagements.models import Engagement, Finding
from app.engagements.schemas import EngagementCreate, EngagementUpdate, EngagementResponse
from app.workflow.template_router import get_template

router = APIRouter(prefix="/api/engagements", tags=["engagements"])


@router.get("", response_model=list[EngagementResponse])
async def list_engagements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Engagement, func.count(Finding.id))
        .outerjoin(Finding, Finding.engagement_id == Engagement.id)
        .group_by(Engagement.id)
        .order_by(Engagement.created_at.desc())
    )
    response = []
    for engagement, finding_count in result.all():
        r = EngagementResponse.model_validate(engagement)
        r.finding_count = finding_count
        response.append(r)
    return response


@router.post("", response_model=EngagementResponse, status_code=201)
async def create_engagement(
    request: EngagementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    assessment_template = None
    if request.template_key:
        assessment_template = await get_template(db, request.template_key)
        if not assessment_template:
            raise HTTPException(status_code=422, detail="Unknown assessment template")
    engagement = Engagement(
        name=request.name,
        client_name=request.client_name,
        scope=request.scope,
        start_date=request.start_date,
        end_date=request.end_date,
        template_key=request.template_key,
        created_by=current_user.id,
    )
    db.add(engagement)
    await db.flush()
    if assessment_template:
        from app.checklists.methodologies import get_methodology_items
        from app.checklists.models import ChecklistItem

        for methodology in assessment_template["methodologies"]:
            for item_data in get_methodology_items(methodology):
                db.add(ChecklistItem(
                    engagement_id=engagement.id,
                    methodology=methodology,
                    category=item_data["category"],
                    item=item_data["item"],
                    description=item_data.get("description"),
                    tools=item_data.get("tools"),
                    techniques=item_data.get("techniques"),
                    reference_url=item_data.get("reference_url"),
                    order_index=item_data.get("order_index", 0),
                ))
        await db.flush()
    return EngagementResponse.model_validate(engagement)


@router.get("/analytics")
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregated analytics across all engagements."""
    from sqlalchemy import func as sqlfunc
    sev_result = await db.execute(
        select(Finding.severity, sqlfunc.count(Finding.id)).group_by(Finding.severity)
    )
    severity_dist = {(k.value if hasattr(k, 'value') else str(k)): v for k, v in sev_result.all()}
    eng_result = await db.execute(
        select(Engagement.name, sqlfunc.count(Finding.id))
        .outerjoin(Finding, Finding.engagement_id == Engagement.id)
        .group_by(Engagement.id)
    )
    per_engagement = [{"name": name, "findings": count} for name, count in eng_result.all()]
    retest_result = await db.execute(
        select(Finding.retest_status, sqlfunc.count(Finding.id))
        .where(Finding.retest_status.isnot(None)).group_by(Finding.retest_status)
    )
    retest_dist = {str(k): v for k, v in retest_result.all()}
    host_findings = await db.execute(select(Finding.affected_hosts).where(Finding.affected_hosts.isnot(None)))
    host_count = {}
    for (hosts,) in host_findings.all():
        if hosts:
            for h in hosts.split(","):
                h = h.strip()
                if h:
                    host_count[h] = host_count.get(h, 0) + 1
    top_hosts = sorted(host_count.items(), key=lambda x: -x[1])[:10]
    source_result = await db.execute(
        select(Finding.source, sqlfunc.count(Finding.id)).group_by(Finding.source)
    )
    source_dist = {str(k or "manual"): v for k, v in source_result.all()}
    return {
        "severity_distribution": severity_dist, "per_engagement": per_engagement,
        "retest_distribution": retest_dist,
        "top_hosts": [{"host": h, "count": c} for h, c in top_hosts],
        "source_distribution": source_dist,
        "total_findings": sum(severity_dist.values()),
        "total_engagements": len(per_engagement),
    }


@router.get("/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Engagement, func.count(Finding.id))
        .outerjoin(Finding, Finding.engagement_id == Engagement.id)
        .where(Engagement.id == engagement_id)
        .group_by(Engagement.id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    engagement, finding_count = row
    r = EngagementResponse.model_validate(engagement)
    r.finding_count = finding_count
    return r


@router.put("/{engagement_id}", response_model=EngagementResponse)
async def update_engagement(
    engagement_id: str,
    request: EngagementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(engagement, field, value)

    if (
        engagement.start_date
        and engagement.end_date
        and engagement.end_date < engagement.start_date
    ):
        raise HTTPException(
            status_code=422,
            detail="End date cannot be before start date",
        )

    await db.flush()
    return EngagementResponse.model_validate(engagement)


@router.delete("/{engagement_id}", status_code=204)
async def delete_engagement(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Delete related data explicitly so cleanup is reliable on every supported database.
    from app.engagements.models import (
        Finding,
        EvidenceAttachment,
        AttackPath,
        Report,
        ScanUpload,
        AppSetting,
        FindingHistory,
        ScanSnapshot,
        ScanObservation,
        EvidenceNote,
        EvidenceNoteAttachment,
    )
    from app.ad.models import ADImport
    from app.checklists.models import ChecklistItem
    from app.jobs.models import Job
    from app.jobs.runner import cleanup_job, stop_job
    from sqlalchemy import delete

    finding_result = await db.execute(
        select(Finding.id).where(Finding.engagement_id == engagement_id)
    )
    finding_ids = list(finding_result.scalars().all())
    if finding_ids:
        await db.execute(
            delete(EvidenceAttachment).where(
                EvidenceAttachment.finding_id.in_(finding_ids)
            )
        )
        await db.execute(
            delete(FindingHistory).where(FindingHistory.finding_id.in_(finding_ids))
        )
    snapshot_result = await db.execute(
        select(ScanSnapshot.id).where(ScanSnapshot.engagement_id == engagement_id)
    )
    snapshot_ids = list(snapshot_result.scalars().all())
    if snapshot_ids:
        await db.execute(
            delete(ScanObservation).where(ScanObservation.snapshot_id.in_(snapshot_ids))
        )
    await db.execute(delete(ScanSnapshot).where(ScanSnapshot.engagement_id == engagement_id))
    note_result = await db.execute(
        select(EvidenceNote.id).where(EvidenceNote.engagement_id == engagement_id)
    )
    note_ids = list(note_result.scalars().all())
    if note_ids:
        await db.execute(
            delete(EvidenceNoteAttachment).where(
                EvidenceNoteAttachment.note_id.in_(note_ids)
            )
        )
    await db.execute(delete(EvidenceNote).where(EvidenceNote.engagement_id == engagement_id))
    await db.execute(delete(Finding).where(Finding.engagement_id == engagement_id))
    await db.execute(delete(AttackPath).where(AttackPath.engagement_id == engagement_id))
    await db.execute(delete(Report).where(Report.engagement_id == engagement_id))
    await db.execute(delete(ScanUpload).where(ScanUpload.engagement_id == engagement_id))
    await db.execute(delete(ADImport).where(ADImport.engagement_id == engagement_id))
    await db.execute(
        delete(ChecklistItem).where(ChecklistItem.engagement_id == engagement_id)
    )
    job_result = await db.execute(
        select(Job.id).where(Job.engagement_id == engagement_id)
    )
    job_ids = list(job_result.scalars().all())
    for job_id in job_ids:
        stop_job(job_id)
        cleanup_job(job_id)
    await db.execute(delete(Job).where(Job.engagement_id == engagement_id))
    await db.execute(
        delete(AppSetting).where(AppSetting.key == f"narrative_{engagement_id}")
    )

    await db.delete(engagement)

    # Clean up files
    import shutil, os
    from app.config import settings
    for subdir in ["uploads", "reports", "notebook"]:
        path = os.path.join(settings.data_dir, subdir, engagement_id)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    for finding_id in finding_ids:
        path = os.path.join(settings.data_dir, "evidence", finding_id)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    for job_id in job_ids:
        path = os.path.join(settings.data_dir, "jobs", job_id)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
