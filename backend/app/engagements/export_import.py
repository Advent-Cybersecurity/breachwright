import json
import logging
import re
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.engagements.models import Engagement, Finding, AttackPath, Report, ScanUpload
from app.engagements.schemas import EngagementCreate, FindingCreate
from pydantic import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements", tags=["export_import"])

MAX_IMPORT_SIZE = 25 * 1024 * 1024
MAX_IMPORT_FINDINGS = 5000
MAX_IMPORT_ATTACK_PATHS = 1000
MAX_ATTACK_PATH_DESCRIPTION_SIZE = 200000
MAX_ATTACK_PATH_STEPS = 1000
MAX_ATTACK_PATH_STEPS_SIZE = 500000
VALID_RETEST_STATUSES = {
    None,
    "",
    "open",
    "remediated",
    "retest_needed",
    "accepted_risk",
}


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

    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", eng.name).strip("._")
    filename = f"{safe_name or 'engagement'}_export.json"
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
    current_user: User = Depends(require_editor),
):
    content = await file.read(MAX_IMPORT_SIZE + 1)
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=413, detail="Import file too large (max 25MB)")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    if not isinstance(data, dict) or "engagement" not in data or "findings" not in data:
        raise HTTPException(status_code=400, detail="Invalid export format: missing engagement or findings")

    eng_data = data["engagement"]
    finding_data = data["findings"]
    attack_path_data = data.get("attack_paths", [])
    if not isinstance(eng_data, dict):
        raise HTTPException(status_code=400, detail="Invalid engagement data")
    if not isinstance(finding_data, list):
        raise HTTPException(status_code=400, detail="Findings must be a list")
    if not isinstance(attack_path_data, list):
        raise HTTPException(status_code=400, detail="Attack paths must be a list")
    if len(finding_data) > MAX_IMPORT_FINDINGS:
        raise HTTPException(
            status_code=413,
            detail=f"Import exceeds {MAX_IMPORT_FINDINGS} findings",
        )
    if len(attack_path_data) > MAX_IMPORT_ATTACK_PATHS:
        raise HTTPException(
            status_code=413,
            detail=f"Import exceeds {MAX_IMPORT_ATTACK_PATHS} attack paths",
        )

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

    try:
        validated_engagement = EngagementCreate(
            name=eng_data.get("name", "Imported Engagement"),
            client_name=eng_data.get("client_name", "Unknown"),
            scope=eng_data.get("scope"),
            start_date=start_date,
            end_date=end_date,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid engagement: {exc.errors()[0]['msg']}",
        ) from exc

    # Create engagement
    engagement = Engagement(
        name=validated_engagement.name,
        client_name=validated_engagement.client_name,
        scope=validated_engagement.scope,
        start_date=validated_engagement.start_date,
        end_date=validated_engagement.end_date,
        created_by=current_user.id,
    )
    db.add(engagement)
    await db.flush()

    # Create findings
    finding_count = 0
    for index, fd in enumerate(finding_data):
        if not isinstance(fd, dict):
            raise HTTPException(
                status_code=422,
                detail=f"Finding {index + 1} must be an object",
            )
        if fd.get("retest_status") not in VALID_RETEST_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Finding {index + 1} has an invalid retest status",
            )
        try:
            validated_finding = FindingCreate(
                title=fd.get("title", "Untitled"),
                description=fd.get("description"),
                severity=fd.get("severity", "info"),
                cvss_score=fd.get("cvss_score"),
                affected_hosts=fd.get("affected_hosts"),
                evidence=fd.get("evidence"),
                remediation=fd.get("remediation"),
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid finding {index + 1}: {exc.errors()[0]['msg']}",
            ) from exc
        finding = Finding(
            engagement_id=engagement.id,
            title=validated_finding.title,
            description=validated_finding.description,
            severity=validated_finding.severity,
            cvss_score=validated_finding.cvss_score,
            affected_hosts=validated_finding.affected_hosts,
            evidence=validated_finding.evidence,
            remediation=validated_finding.remediation,
            source="imported",
            retest_status=fd.get("retest_status"),
            created_by=current_user.id,
        )
        db.add(finding)
        finding_count += 1

    # Create attack paths
    ap_count = 0
    for index, apd in enumerate(attack_path_data):
        if not isinstance(apd, dict):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} must be an object",
            )
        name = str(apd.get("name", "Unnamed")).strip()
        if not name or len(name) > 500:
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has an invalid name",
            )
        description = apd.get("description")
        if description is not None and (
            not isinstance(description, str)
            or len(description) > MAX_ATTACK_PATH_DESCRIPTION_SIZE
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has an invalid description",
            )
        steps = apd.get("steps")
        if steps is not None and (
            not isinstance(steps, list)
            or len(steps) > MAX_ATTACK_PATH_STEPS
            or len(json.dumps(steps).encode("utf-8")) > MAX_ATTACK_PATH_STEPS_SIZE
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has invalid steps",
            )
        risk_level = apd.get("risk_level")
        if risk_level is not None and (
            not isinstance(risk_level, str) or len(risk_level) > 50
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has an invalid risk level",
            )
        ap = AttackPath(
            engagement_id=engagement.id,
            name=name,
            description=description,
            steps=steps,
            risk_level=risk_level,
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
