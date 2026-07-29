import json
import logging
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.engagements.models import Engagement, Finding, AttackPath, Report, ScanUpload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements", tags=["export_import"])


def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


@router.get("/{engagement_id}/export")
async def export_engagement(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get engagement
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Get findings
    result = await db.execute(select(Finding).where(Finding.engagement_id == engagement_id))
    findings = result.scalars().all()

    # Get attack paths
    result = await db.execute(select(AttackPath).where(AttackPath.engagement_id == engagement_id))
    attack_paths = result.scalars().all()

    export_data = {
        "version": "1.0",
        "exported_by": current_user.display_name,
        "engagement": {
            "name": eng.name,
            "client_name": eng.client_name,
            "scope": eng.scope,
            "status": eng.status.value if hasattr(eng.status, 'value') else eng.status,
            "start_date": _serialize(eng.start_date) if eng.start_date else None,
            "end_date": _serialize(eng.end_date) if eng.end_date else None,
        },
        "findings": [
            {
                "title": f.title,
                "description": f.description,
                "severity": f.severity.value if hasattr(f.severity, 'value') else f.severity,
                "cvss_score": float(f.cvss_score) if f.cvss_score else None,
                "affected_hosts": f.affected_hosts,
                "evidence": f.evidence,
                "remediation": f.remediation,
                "source": f.source,
                "retest_status": f.retest_status,
            }
            for f in findings
        ],
        "attack_paths": [
            {
                "name": ap.name,
                "description": ap.description,
                "steps": ap.steps,
                "risk_level": ap.risk_level,
            }
            for ap in attack_paths
        ],
    }

    filename = f"{eng.name.replace(' ', '_').lower()}_export.json"
    content = json.dumps(export_data, indent=2, default=_serialize)

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_engagement(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    if "engagement" not in data or "findings" not in data:
        raise HTTPException(status_code=400, detail="Invalid export format: missing engagement or findings")

    eng_data = data["engagement"]

    # Parse dates
    start_date = None
    end_date = None
    if eng_data.get("start_date"):
        try:
            start_date = date.fromisoformat(eng_data["start_date"])
        except (ValueError, TypeError):
            pass
    if eng_data.get("end_date"):
        try:
            end_date = date.fromisoformat(eng_data["end_date"])
        except (ValueError, TypeError):
            pass

    # Create engagement
    engagement = Engagement(
        name=eng_data.get("name", "Imported Engagement"),
        client_name=eng_data.get("client_name", "Unknown"),
        scope=eng_data.get("scope"),
        start_date=start_date,
        end_date=end_date,
        created_by=current_user.id,
    )
    db.add(engagement)
    await db.flush()

    # Create findings
    finding_count = 0
    for fd in data.get("findings", []):
        finding = Finding(
            engagement_id=engagement.id,
            title=fd.get("title", "Untitled"),
            description=fd.get("description"),
            severity=fd.get("severity", "info"),
            cvss_score=fd.get("cvss_score"),
            affected_hosts=fd.get("affected_hosts"),
            evidence=fd.get("evidence"),
            remediation=fd.get("remediation"),
            source=fd.get("source", "imported"),
            retest_status=fd.get("retest_status"),
            created_by=current_user.id,
        )
        db.add(finding)
        finding_count += 1

    # Create attack paths
    ap_count = 0
    for apd in data.get("attack_paths", []):
        ap = AttackPath(
            engagement_id=engagement.id,
            name=apd.get("name", "Unnamed"),
            description=apd.get("description"),
            steps=apd.get("steps"),
            risk_level=apd.get("risk_level"),
        )
        db.add(ap)
        ap_count += 1

    await db.flush()

    logger.info(
        "Imported engagement '%s' with %d findings and %d attack paths",
        engagement.name, finding_count, ap_count,
    )

    return {
        "id": engagement.id,
        "name": engagement.name,
        "findings_imported": finding_count,
        "attack_paths_imported": ap_count,
    }
