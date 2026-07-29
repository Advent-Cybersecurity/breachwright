import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.engagements.models import Engagement, Finding, AttackPath, Report
from app.engagements.schemas import ReportResponse
from app.ai.provider import get_provider
from app.ai.prompts.loader import get_prompt
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


@router.get("/api/engagements/{engagement_id}/reports", response_model=list[ReportResponse])
async def list_reports(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Report).where(Report.engagement_id == engagement_id).order_by(Report.created_at.desc())
    )
    return [ReportResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/api/engagements/{engagement_id}/reports", response_model=ReportResponse, status_code=201)
async def generate_report(
    engagement_id: str,
    format: str = Query(default="md", pattern="^(md|docx)$"),
    template_id: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    finding_result = await db.execute(select(Finding).where(Finding.engagement_id == engagement_id))
    findings = finding_result.scalars().all()

    ap_result = await db.execute(select(AttackPath).where(AttackPath.engagement_id == engagement_id))
    attack_paths = ap_result.scalars().all()

    # Build AI context
    findings_text = "\n\n".join(
        f"### {f.title}\n"
        f"Severity: {f.severity.upper() if isinstance(f.severity, str) else f.severity.value.upper()} | "
        f"CVSS: {f.cvss_score or 'N/A'}\n"
        f"Affected: {f.affected_hosts or 'N/A'}\n"
        f"Description: {f.description or 'N/A'}\n"
        f"Evidence: {f.evidence or 'N/A'}\n"
        f"Remediation: {f.remediation or 'N/A'}"
        for f in findings
    )

    ap_text = ""
    if attack_paths:
        ap_text = "\n\nAttack Paths:\n" + "\n\n".join(
            f"### {ap.name} (Risk: {ap.risk_level or 'N/A'})\n{ap.description or 'N/A'}"
            for ap in attack_paths
        )

    user_message = (
        f"Engagement: {engagement.name}\n"
        f"Client: {engagement.client_name}\n"
        f"Scope: {engagement.scope or 'Not specified'}\n"
        f"Start: {engagement.start_date or 'N/A'}\n"
        f"End: {engagement.end_date or 'N/A'}\n\n"
        f"Findings ({len(findings)} total):\n\n{findings_text}{ap_text}"
    )

    provider = get_provider()
    system_prompt = await get_prompt(db, "prompt_reports")
    try:
        report_content = await provider.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=8192,
        )
    except Exception as e:
        logger.error("AI provider error: %s", e)
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}")

    # Save report
    report_dir = os.path.join(settings.data_dir, "reports", engagement_id)
    os.makedirs(report_dir, exist_ok=True)

    report = Report(
        engagement_id=engagement_id,
        title=f"{engagement.name} - Penetration Test Report",
        format=format,
        generated_by=current_user.id,
    )
    db.add(report)
    await db.flush()

    if format == "docx":
        from app.reports.docx_generator import generate_docx_report
        from app.reports.template_model import ReportTemplate

        # Load template if specified, or use default
        template = None
        if template_id:
            t_result = await db.execute(select(ReportTemplate).where(ReportTemplate.id == template_id))
            template = t_result.scalar_one_or_none()
        elif not template_id:
            t_result = await db.execute(select(ReportTemplate).where(ReportTemplate.is_default == True).limit(1))
            template = t_result.scalar_one_or_none()

        file_path = os.path.join(report_dir, f"report-{report.id}.docx")
        try:
            generate_docx_report(engagement, findings, attack_paths, report_content, file_path, template=template)
        except Exception as e:
            logger.error("DOCX generation error: %s", e)
            # Fall back to markdown
            file_path = os.path.join(report_dir, f"report-{report.id}.md")
            with open(file_path, "w") as f:
                f.write(report_content)
            report.format = "md"
    else:
        file_path = os.path.join(report_dir, f"report-{report.id}.md")
        with open(file_path, "w") as f:
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
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.file_path and os.path.exists(report.file_path):
        try:
            os.remove(report.file_path)
        except Exception:
            pass
    await db.delete(report)
