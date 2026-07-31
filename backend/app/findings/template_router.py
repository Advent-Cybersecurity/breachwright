"""Local CRUD and versioned interchange for reusable finding templates."""

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.db.session import get_db
from app.engagements.models import FindingTemplate, Severity


router = APIRouter(prefix="/api/finding-templates", tags=["finding_templates"])
MAX_TEMPLATE_IMPORT_BYTES = 512 * 1024


class FindingTemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: Optional[str] = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=200000)
    severity: Severity = Severity.info
    cvss_score: Optional[float] = Field(default=None, ge=0, le=10)
    remediation: Optional[str] = Field(default=None, max_length=200000)

    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


class FindingTemplateDocument(BaseModel):
    kind: Literal["breachwright-finding-template"]
    version: Literal["1.0"]
    template: FindingTemplateInput

    model_config = {"extra": "forbid"}


def template_response(template: FindingTemplate) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "category": template.category,
        "title": template.title,
        "description": template.description,
        "severity": template.severity.value if hasattr(template.severity, "value") else template.severity,
        "cvss_score": float(template.cvss_score) if template.cvss_score is not None else None,
        "remediation": template.remediation,
        "schema_version": template.schema_version,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def apply_input(template: FindingTemplate, body: FindingTemplateInput) -> None:
    template.name = body.name
    template.category = body.category
    template.title = body.title
    template.description = body.description
    template.severity = body.severity
    template.cvss_score = body.cvss_score
    template.remediation = body.remediation


@router.get("")
async def list_finding_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    templates = list((await db.execute(
        select(FindingTemplate).order_by(
            FindingTemplate.category.is_(None),
            FindingTemplate.category,
            FindingTemplate.name,
            FindingTemplate.id,
        )
    )).scalars().all())
    return [template_response(template) for template in templates]


@router.post("", status_code=201)
async def create_finding_template(
    body: FindingTemplateInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    template = FindingTemplate(schema_version=1)
    apply_input(template, body)
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template_response(template)


@router.put("/{template_id}")
async def update_finding_template(
    template_id: str,
    body: FindingTemplateInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    template = (await db.execute(
        select(FindingTemplate).where(FindingTemplate.id == template_id)
    )).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Finding template not found")
    apply_input(template, body)
    await db.flush()
    await db.refresh(template)
    return template_response(template)


@router.delete("/{template_id}", status_code=204)
async def delete_finding_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    template = (await db.execute(
        select(FindingTemplate).where(FindingTemplate.id == template_id)
    )).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Finding template not found")
    await db.delete(template)


@router.post("/import", status_code=201)
async def import_finding_template(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    content = await file.read(MAX_TEMPLATE_IMPORT_BYTES + 1)
    if len(content) > MAX_TEMPLATE_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Finding template file is too large")
    try:
        document = FindingTemplateDocument.model_validate_json(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid or unsupported finding template") from exc
    template = FindingTemplate(schema_version=1)
    apply_input(template, document.template)
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template_response(template)


@router.get("/{template_id}/export")
async def export_finding_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = (await db.execute(
        select(FindingTemplate).where(FindingTemplate.id == template_id)
    )).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Finding template not found")
    response = template_response(template)
    document = {
        "kind": "breachwright-finding-template",
        "version": "1.0",
        "template": {
            key: response[key]
            for key in ("name", "category", "title", "description", "severity", "cvss_score", "remediation")
        },
    }
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", template.name).strip("-") or "finding-template"
    return JSONResponse(
        document,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.breachwright-finding.json"'},
    )
