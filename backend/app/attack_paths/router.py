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
from app.ai.output_validation import validate_ai_attack_paths
from app.ai.completion import complete_validated_json
from app.ai.prompts.loader import get_prompt
from app.ai.prompts.templates import ATTACK_PATH_GROUNDING_RULES
from app.ai.context import AIContextTooLarge, build_bounded_untrusted_context
from app.ai.errors import AI_PROVIDER_FAILURE_MESSAGE

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

    # Build findings summary for AI
    findings_text = "\n".join(
        f"- finding_id={f.id} [{f.severity.upper()}] {f.title} "
        f"(CVSS: {f.cvss_score if f.cvss_score is not None else 'N/A'}) "
        f"Hosts: {f.affected_hosts or 'N/A'}\n  Description: {f.description or 'N/A'}"
        for f in findings
    )

    finding_context = (
        f"Engagement: {engagement.name}\n"
        f"Client: {engagement.client_name}\n"
        f"Scope: {engagement.scope or 'Not specified'}\n\n"
        f"Findings:\n{findings_text}\n"
    )
    try:
        user_message = build_bounded_untrusted_context(
            "untrusted_finding_data",
            finding_context,
            label="Attack-path finding data",
        )
    except AIContextTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    system_prompt = await get_prompt(db, "prompt_attack_paths") + ATTACK_PATH_GROUNDING_RULES
    try:
        provider = get_provider()
        validated_paths, metadata = await complete_validated_json(
            provider,
            system_prompt=system_prompt,
            user_message=user_message,
            validator=validate_ai_attack_paths,
        )
    except Exception as exc:
        logger.warning("Attack-path AI request failed with %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=AI_PROVIDER_FAILURE_MESSAGE) from exc

    findings_by_id = {finding.id: finding for finding in findings}
    grounded_paths = []
    for validated in validated_paths:
        if len(validated.steps) < 2:
            continue
        if any(
            not step.finding_id or step.finding_id not in findings_by_id
            for step in validated.steps
        ):
            continue
        grounded_paths.append(validated)

    if validated_paths and not grounded_paths:
        raise HTTPException(
            status_code=502,
            detail="AI returned exploitation chains without valid finding citations",
        )

    # Replacement is atomic from the user's perspective: existing chains are
    # removed only after a complete, grounded replacement has been validated.
    await db.execute(delete(AttackPath).where(AttackPath.engagement_id == engagement_id))

    created = []
    for validated in grounded_paths:
        referenced_findings = [findings_by_id[step.finding_id] for step in validated.steps]
        target_hosts = ", ".join(
            sorted(
                {
                    host.strip()
                    for finding in referenced_findings
                    for host in (finding.affected_hosts or "").split(",")
                    if host.strip()
                }
            )
        )
        description = validated.description or ""
        if target_hosts:
            description = f"[Targets: {target_hosts}]\n\n{description}"

        attack_path = AttackPath(
            engagement_id=engagement_id,
            name=validated.name,
            description=description,
            steps=[step.model_dump(mode="json") for step in validated.steps],
            risk_level=validated.risk_level,
        )
        db.add(attack_path)
        await db.flush()
        created.append(AttackPathResponse.model_validate(attack_path))

    logger.info(
        "Generated %d grounded attack paths for engagement %s in %d ms",
        len(created),
        engagement_id,
        metadata.latency_ms,
    )
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
