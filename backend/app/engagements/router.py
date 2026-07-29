from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.engagements.models import Engagement, Finding
from app.engagements.schemas import EngagementCreate, EngagementUpdate, EngagementResponse

router = APIRouter(prefix="/api/engagements", tags=["engagements"])


@router.get("", response_model=list[EngagementResponse])
async def list_engagements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Engagement).order_by(Engagement.created_at.desc())
    )
    engagements = result.scalars().all()
    response = []
    for eng in engagements:
        r = EngagementResponse.model_validate(eng)
        r.finding_count = len(eng.findings) if eng.findings else 0
        response.append(r)
    return response


@router.post("", response_model=EngagementResponse, status_code=201)
async def create_engagement(
    request: EngagementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    engagement = Engagement(
        name=request.name,
        client_name=request.client_name,
        scope=request.scope,
        start_date=request.start_date,
        end_date=request.end_date,
        created_by=current_user.id,
    )
    db.add(engagement)
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
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    r = EngagementResponse.model_validate(engagement)
    r.finding_count = len(engagement.findings) if engagement.findings else 0
    return r


@router.put("/{engagement_id}", response_model=EngagementResponse)
async def update_engagement(
    engagement_id: str,
    request: EngagementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(engagement, field, value)

    await db.flush()
    return EngagementResponse.model_validate(engagement)


@router.delete("/{engagement_id}", status_code=204)
async def delete_engagement(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Delete related data (findings, attack paths, reports, scans, AD data, jobs)
    from app.engagements.models import Finding, AttackPath, Report, ScanUpload
    await db.execute(select(Finding).where(Finding.engagement_id == engagement_id))
    from sqlalchemy import delete
    await db.execute(delete(Finding).where(Finding.engagement_id == engagement_id))
    await db.execute(delete(AttackPath).where(AttackPath.engagement_id == engagement_id))
    await db.execute(delete(Report).where(Report.engagement_id == engagement_id))
    await db.execute(delete(ScanUpload).where(ScanUpload.engagement_id == engagement_id))

    try:
        from app.ad.models import ADImport
        await db.execute(delete(ADImport).where(ADImport.engagement_id == engagement_id))
    except Exception:
        pass

    try:
        from app.jobs.models import Job
        await db.execute(delete(Job).where(Job.engagement_id == engagement_id))
    except Exception:
        pass

    await db.delete(engagement)

    # Clean up files
    import shutil, os
    from app.config import settings
    for subdir in ["uploads", "reports"]:
        path = os.path.join(settings.data_dir, subdir, engagement_id)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
