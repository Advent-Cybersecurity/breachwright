import asyncio
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.engagements.models import Engagement, Finding, AttackPath, Report
from app.engagements.schemas import ReportResponse
from app.ai.provider import get_provider
from app.ai.prompts.loader import get_prompt
from app.ai.prompts.templates import REPORT_GROUNDING_RULES
from app.ai.context import (
    AIContextTooLarge,
    MAX_GENERATIVE_CONTEXT_CHARS,
    build_bounded_untrusted_context,
)
from app.ai.errors import AI_PROVIDER_FAILURE_MESSAGE
from app.config import settings
from app.reports.content import build_report_content

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


async def _load_report_source(engagement_id: str, db: AsyncSession):
    engagement = (await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )).scalar_one_or_none()
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")

    findings = (await db.execute(
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
    )).scalars().all()

    attack_paths = (await db.execute(
        select(AttackPath)
        .where(AttackPath.engagement_id == engagement_id)
        .order_by(
            case(
                (AttackPath.risk_level == "critical", 0),
                (AttackPath.risk_level == "high", 1),
                (AttackPath.risk_level == "medium", 2),
                (AttackPath.risk_level == "low", 3),
                else_=4,
            ),
            AttackPath.created_at,
            AttackPath.id,
        )
    )).scalars().all()
    return engagement, findings, attack_paths


@router.get("/api/engagements/{engagement_id}/reports", response_model=list[ReportResponse])
async def list_reports(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    engagement = (await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )).scalar_one_or_none()
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    result = await db.execute(
        select(Report).where(Report.engagement_id == engagement_id).order_by(Report.created_at.desc())
    )
    return [ReportResponse.model_validate(r) for r in result.scalars().all()]


@router.get("/api/engagements/{engagement_id}/reports/ai-preflight")
async def report_ai_preflight(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Describe an AI report request without initializing or calling a provider."""
    engagement, findings, attack_paths = await _load_report_source(engagement_id, db)
    context_chars = len(build_report_content(engagement, findings, attack_paths))
    issues = []
    if context_chars > MAX_GENERATIVE_CONTEXT_CHARS:
        issues.append(
            "The report source exceeds the AI context limit. Generate it locally "
            "or reduce the engagement content first."
        )
    provider = settings.ai_provider.lower()
    return {
        "provider": provider,
        "external_provider": provider not in {
            "local", "ollama", "vllm", "llamacpp", "lmstudio"
        },
        "redaction_enabled": settings.ai_redact_sensitive_data,
        "context_chars": context_chars,
        "max_context_chars": MAX_GENERATIVE_CONTEXT_CHARS,
        "finding_count": len(findings),
        "attack_path_count": len(attack_paths),
        "ready": not issues,
        "issues": issues,
    }


@router.post("/api/engagements/{engagement_id}/reports", response_model=ReportResponse, status_code=201)
async def generate_report(
    engagement_id: str,
    format: str = Query(default="md", pattern="^(md|docx)$"),
    template_id: str = Query(default=None),
    use_ai: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    engagement, findings, attack_paths = await _load_report_source(engagement_id, db)

    template = None
    if format == "docx":
        from app.reports.template_model import ReportTemplate

        if template_id:
            template = (await db.execute(
                select(ReportTemplate).where(ReportTemplate.id == template_id)
            )).scalar_one_or_none()
            if template is None:
                raise HTTPException(status_code=404, detail="Report template not found")
        else:
            template = (await db.execute(
                select(ReportTemplate)
                .where(ReportTemplate.is_default.is_(True))
                .order_by(ReportTemplate.created_at.desc(), ReportTemplate.id)
                .limit(1)
            )).scalar_one_or_none()

    report_content = build_report_content(engagement, findings, attack_paths)
    if use_ai:
        try:
            user_message = build_bounded_untrusted_context(
                "untrusted_report_data",
                report_content,
                label="Report",
            )
        except AIContextTooLarge as exc:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"{exc}. Generate the report locally or reduce the "
                    "engagement content first."
                ),
            ) from exc
        system_prompt = await get_prompt(db, "prompt_reports") + REPORT_GROUNDING_RULES
        required_evidence_ids = {
            str(ref.get("id"))
            for finding in findings
            for ref in (finding.evidence_refs or [])
            if ref.get("id")
        }
        required_finding_titles = {finding.title for finding in findings}
        try:
            provider = get_provider()
            generated_content = await provider.complete(
                system_prompt=system_prompt,
                user_message=user_message,
                max_tokens=8192,
            )
        except Exception as exc:
            logger.warning("AI report request failed with %s", type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail=(
                    f"{AI_PROVIDER_FAILURE_MESSAGE} You can also generate the "
                    "report locally."
                ),
            ) from exc

        missing_ids = sorted(
            evidence_id
            for evidence_id in required_evidence_ids
            if evidence_id not in generated_content
        )
        missing_titles = sorted(
            title for title in required_finding_titles if title not in generated_content
        )
        if missing_ids or missing_titles:
            logger.warning(
                "Rejected AI report that omitted %d evidence IDs and %d finding titles",
                len(missing_ids),
                len(missing_titles),
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "AI output failed evidence validation and was not saved. Try "
                    "again, or generate the report locally."
                ),
            )
        report_content = generated_content
    report_content = report_content.replace("\u2014", "-")

    # Save report
    report_dir = os.path.join(settings.data_dir, "reports", engagement_id)
    os.makedirs(report_dir, exist_ok=True)

    report = Report(
        engagement_id=engagement_id,
        title=f"{engagement.name} - Penetration Test Report",
        format=format,
        template_used=template.name if template else None,
        generated_by=current_user.id,
    )
    db.add(report)
    await db.flush()

    if format == "docx":
        from app.reports.docx_generator import generate_docx_report

        file_path = os.path.join(report_dir, f"report-{report.id}.docx")
        try:
            await asyncio.to_thread(
                generate_docx_report,
                engagement,
                findings,
                attack_paths,
                report_content,
                file_path,
                template=template,
            )
        except Exception as e:
            logger.error("DOCX generation error: %s", e)
            # Fall back to markdown
            file_path = os.path.join(report_dir, f"report-{report.id}.md")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            report.format = "md"
            report.template_used = None
    else:
        file_path = os.path.join(report_dir, f"report-{report.id}.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report_content)

    report.file_path = file_path
    await db.flush()

    logger.info("Generated %s report %s for engagement %s", format, report.id, engagement_id)
    return ReportResponse.model_validate(report)


@router.get("/api/reports/{report_id}/download")
async def download_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="Report file not found")

    media_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "md": "text/markdown",
    }

    return FileResponse(
        report.file_path,
        filename=f"{report.title}.{report.format}",
        media_type=media_types.get(report.format, "application/octet-stream"),
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/api/reports/{report_id}", status_code=204)
async def delete_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.file_path and os.path.exists(report.file_path):
        try:
            os.remove(report.file_path)
        except OSError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Report file could not be removed: {exc}",
            ) from exc
    await db.delete(report)
