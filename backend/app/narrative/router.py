"""Attack Narrative Generation — API Endpoints.

Provides:
  - Per-path narrative generation (individual attack story)
  - Engagement-wide narrative (unified assessment story)
  - Narrative retrieval for report embedding
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.ai.errors import AI_PROVIDER_FAILURE_MESSAGE
from app.engagements.models import AttackPath, Engagement
from app.narrative.service import (
    generate_all_narratives,
    generate_engagement_narrative,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements/{engagement_id}/narrative", tags=["narrative"])
MAX_SAVED_NARRATIVE_SIZE = 2 * 1024 * 1024


async def _require_engagement(engagement_id: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(Engagement.id).where(Engagement.id == engagement_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")


@router.post("/paths")
async def generate_path_narratives(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Generate narratives for each attack path in the engagement.

    Each attack path gets its own technical narrative with MITRE ATT&CK
    mapping, executive summary, and impact assessment.
    Requires attack paths to exist — run "Generate Exploitation Chains" first.
    """
    results = await generate_all_narratives(db, engagement_id)

    if len(results) == 1 and "error" in results[0]:
        if "not found" in results[0]["error"].lower():
            raise HTTPException(status_code=404, detail=results[0]["error"])
        if results[0]["error"] == AI_PROVIDER_FAILURE_MESSAGE:
            raise HTTPException(status_code=502, detail=results[0]["error"])
        if "supports up to" in results[0]["error"] or "exceeds the" in results[0]["error"]:
            raise HTTPException(status_code=413, detail=results[0]["error"])
        raise HTTPException(status_code=400, detail=results[0]["error"])

    return {
        "narratives": results,
        "generated": sum(1 for r in results if "error" not in r),
        "failed": sum(1 for r in results if "error" in r),
    }


@router.post("/full")
async def generate_full_narrative(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Generate a unified narrative covering the entire engagement.

    Weaves all findings and attack paths into a single coherent story
    suitable for the report's main assessment narrative section.
    Does NOT require attack paths — works with findings alone.
    """
    result = await generate_engagement_narrative(db, engagement_id)

    if "error" in result:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        if result["error"] == AI_PROVIDER_FAILURE_MESSAGE:
            raise HTTPException(status_code=502, detail=result["error"])
        if "supports up to" in result["error"] or "exceeds the" in result["error"]:
            raise HTTPException(status_code=413, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.get("/paths")
async def get_path_narratives(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve previously generated narratives for all attack paths."""
    await _require_engagement(engagement_id, db)
    result = await db.execute(
        select(AttackPath)
        .where(AttackPath.engagement_id == engagement_id)
        .order_by(AttackPath.created_at.desc())
    )
    paths = result.scalars().all()

    return [
        {
            "attack_path_id": p.id,
            "name": p.name,
            "risk_level": p.risk_level,
            "narrative": p.narrative,
            "mitre_techniques": p.mitre_techniques,
            "has_narrative": bool(p.narrative),
        }
        for p in paths
    ]

@router.post("/full/save")
async def save_full_narrative(
    engagement_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Save a generated full narrative to the database."""
    from app.engagements.models import AppSetting
    import json
    await _require_engagement(engagement_id, db)
    key = f"narrative_{engagement_id}"
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == key)
    )
    setting = result.scalar_one_or_none()
    value = json.dumps(body)
    if len(value.encode("utf-8")) > MAX_SAVED_NARRATIVE_SIZE:
        raise HTTPException(status_code=413, detail="Narrative is too large")
    if setting:
        setting.value = value
    else:
        setting = AppSetting(key=key, value=value)
        db.add(setting)
    await db.flush()
    return {"status": "saved"}


@router.get("/full")
async def get_saved_narrative(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a previously saved full narrative."""
    from app.engagements.models import AppSetting
    import json
    await _require_engagement(engagement_id, db)
    key = f"narrative_{engagement_id}"
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == key)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        return None
    try:
        return json.loads(setting.value)
    except Exception:
        return None

@router.delete("/full", status_code=204)
async def delete_full_narrative(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Delete the saved full narrative for an engagement."""
    from app.engagements.models import AppSetting
    await _require_engagement(engagement_id, db)
    key = f"narrative_{engagement_id}"
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == key)
    )
    setting = result.scalar_one_or_none()
    if setting:
        await db.delete(setting)
