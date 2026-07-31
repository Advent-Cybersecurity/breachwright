import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.engagements.models import Engagement, Finding, AttackPath
from app.engagements.schemas import AttackPathResponse
from app.ai.provider import get_provider
from app.ai.prompts.loader import get_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements/{engagement_id}/attack-paths", tags=["attack_paths"])


@router.get("", response_model=list[AttackPathResponse])
async def list_attack_paths(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AttackPath)
        .where(AttackPath.engagement_id == engagement_id)
        .order_by(AttackPath.created_at.desc())
    )
    return [AttackPathResponse.model_validate(ap) for ap in result.scalars().all()]


@router.post("", response_model=list[AttackPathResponse], status_code=201)
async def generate_attack_paths(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    # Get engagement
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Get findings
    finding_result = await db.execute(
        select(Finding).where(Finding.engagement_id == engagement_id)
    )
    findings = finding_result.scalars().all()
    if len(findings) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 findings to generate attack paths")

    # Delete existing attack paths for this engagement (replace mode)
    await db.execute(
        delete(AttackPath).where(AttackPath.engagement_id == engagement_id)
    )
    logger.info("Cleared existing attack paths for engagement %s", engagement_id)

    # Build findings summary for AI
    findings_text = "\n".join(
        f"- [{f.severity.upper()}] {f.title} (CVSS: {f.cvss_score or 'N/A'}) "
        f"Hosts: {f.affected_hosts or 'N/A'}\n  Description: {f.description or 'N/A'}"
        for f in findings
    )

    user_message = (
        f"Engagement: {engagement.name}\n"
        f"Client: {engagement.client_name}\n"
        f"Scope: {engagement.scope or 'Not specified'}\n\n"
        f"Findings:\n{findings_text}"
    )

    provider = get_provider()
    system_prompt = await get_prompt(db, "prompt_attack_paths")
    try:
        response_text = await provider.complete(
            system_prompt=system_prompt,
            user_message=user_message,
        )
    except Exception as e:
        logger.error("AI provider error: %s", e)
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}")

    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        paths_data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("Failed to parse AI response as JSON")
        raise HTTPException(status_code=502, detail="AI returned invalid JSON response")

    created = []
    for pd in paths_data:
        # Build description with target hosts prepended
        target_hosts = pd.get("target_hosts", "")
        description = pd.get("description", "")
        if target_hosts:
            description = f"[Targets: {target_hosts}]\n\n{description}"

        attack_path = AttackPath(
            engagement_id=engagement_id,
            name=pd.get("name", "Unnamed Path"),
            description=description,
            steps=pd.get("steps"),
            risk_level=pd.get("risk_level"),
        )
        db.add(attack_path)
        await db.flush()
        created.append(AttackPathResponse.model_validate(attack_path))

    logger.info("Generated %d attack paths for engagement %s (replaced previous)", len(created), engagement_id)
    return created


@router.delete("", status_code=204)
async def clear_attack_paths(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    await db.execute(
        delete(AttackPath).where(AttackPath.engagement_id == engagement_id)
    )
