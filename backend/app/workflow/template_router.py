"""Safe local CRUD and interchange for assessment templates."""

import re
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.checklists.methodologies import get_available_methodologies
from app.db.session import get_db
from app.engagements.models import AssessmentTemplate
from app.workflow.templates import ENGAGEMENT_TEMPLATES


router = APIRouter(prefix="/api/assessment-templates", tags=["assessment_templates"])
MAX_TEMPLATE_IMPORT_BYTES = 64 * 1024
MethodologyKey = Literal[
    "owasp_top10",
    "owasp_api_top10",
    "ptes",
    "nist_800_115",
    "network_pentest",
]


class TemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    methodologies: list[MethodologyKey] = Field(min_length=1, max_length=5)

    model_config = {"str_strip_whitespace": True}

    @field_validator("methodologies")
    @classmethod
    def methodologies_are_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Methodologies must be unique")
        return value


class TemplateDocument(BaseModel):
    kind: Literal["breachwright-assessment-template"]
    version: Literal["1.0"]
    template: TemplateInput


def _built_in_response(key: str, value: dict) -> dict:
    return {
        "key": key,
        "name": value["name"],
        "description": value["description"],
        "methodologies": value["methodologies"],
        "schema_version": 1,
        "built_in": True,
    }


def _user_response(template: AssessmentTemplate) -> dict:
    return {
        "key": template.key,
        "name": template.name,
        "description": template.description,
        "methodologies": template.methodologies,
        "schema_version": template.schema_version,
        "built_in": False,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


async def get_template(db: AsyncSession, template_key: str) -> dict | None:
    if template_key in ENGAGEMENT_TEMPLATES:
        return _built_in_response(template_key, ENGAGEMENT_TEMPLATES[template_key])
    template = (await db.execute(
        select(AssessmentTemplate).where(AssessmentTemplate.key == template_key)
    )).scalar_one_or_none()
    return _user_response(template) if template else None


@router.get("")
async def list_assessment_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_templates = list((await db.execute(
        select(AssessmentTemplate).order_by(AssessmentTemplate.name, AssessmentTemplate.key)
    )).scalars().all())
    return [
        *[_built_in_response(key, value) for key, value in ENGAGEMENT_TEMPLATES.items()],
        *[_user_response(template) for template in user_templates],
    ]


@router.get("/methodologies")
async def list_template_methodologies(
    current_user: User = Depends(get_current_user),
):
    return get_available_methodologies()


@router.post("", status_code=201)
async def create_assessment_template(
    body: TemplateInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    template = AssessmentTemplate(
        key=f"user-{uuid.uuid4()}",
        name=body.name,
        description=body.description,
        methodologies=body.methodologies,
        schema_version=1,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return _user_response(template)


@router.put("/{template_key}")
async def update_assessment_template(
    template_key: str,
    body: TemplateInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    if template_key in ENGAGEMENT_TEMPLATES:
        raise HTTPException(status_code=409, detail="Built-in templates are immutable")
    template = (await db.execute(
        select(AssessmentTemplate).where(AssessmentTemplate.key == template_key)
    )).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Assessment template not found")
    template.name = body.name
    template.description = body.description
    template.methodologies = body.methodologies
    await db.flush()
    await db.refresh(template)
    return _user_response(template)


@router.delete("/{template_key}", status_code=204)
async def delete_assessment_template(
    template_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    if template_key in ENGAGEMENT_TEMPLATES:
        raise HTTPException(status_code=409, detail="Built-in templates cannot be deleted")
    template = (await db.execute(
        select(AssessmentTemplate).where(AssessmentTemplate.key == template_key)
    )).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Assessment template not found")
    await db.delete(template)


@router.post("/import", status_code=201)
async def import_assessment_template(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    content = await file.read(MAX_TEMPLATE_IMPORT_BYTES + 1)
    if len(content) > MAX_TEMPLATE_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Assessment template file is too large")
    try:
        document = TemplateDocument.model_validate_json(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid or unsupported assessment template") from exc
    template = AssessmentTemplate(
        key=f"user-{uuid.uuid4()}",
        name=document.template.name,
        description=document.template.description,
        methodologies=document.template.methodologies,
        schema_version=1,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return _user_response(template)


@router.get("/{template_key}/export")
async def export_assessment_template(
    template_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = await get_template(db, template_key)
    if not template:
        raise HTTPException(status_code=404, detail="Assessment template not found")
    document = {
        "kind": "breachwright-assessment-template",
        "version": "1.0",
        "template": {
            "name": template["name"],
            "description": template["description"],
            "methodologies": template["methodologies"],
        },
    }
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", template["name"]).strip("-") or "assessment-template"
    return JSONResponse(
        document,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.breachwright-template.json"'},
    )
