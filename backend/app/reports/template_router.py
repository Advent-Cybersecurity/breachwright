import os
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.reports.template_model import ReportTemplate
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/report-templates", tags=["report_templates"])

MAX_LOGO_SIZE = 5 * 1024 * 1024


def _validated_logo(logo: UploadFile, content: bytes) -> tuple[str, str]:
    ext = os.path.splitext(logo.filename or "")[1].lower()
    if len(content) > MAX_LOGO_SIZE:
        raise HTTPException(status_code=413, detail="Logo too large (max 5MB)")
    if ext == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ext, "image/png"
    if ext in (".jpg", ".jpeg") and content.startswith(b"\xff\xd8\xff"):
        return ext, "image/jpeg"
    raise HTTPException(
        status_code=400,
        detail="Logo must be a valid PNG or JPG image",
    )


@router.get("")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ReportTemplate).order_by(ReportTemplate.created_at.desc()))
    templates = result.scalars().all()
    return [_template_to_dict(t) for t in templates]


@router.post("", status_code=201)
async def create_template(
    name: str = Form(..., min_length=1, max_length=120),
    company_name: str = Form(default="", max_length=120),
    primary_color: str = Form(default="#dc2626", pattern=r"^#[0-9A-Fa-f]{6}$"),
    secondary_color: str = Form(default="#1a1a25", pattern=r"^#[0-9A-Fa-f]{6}$"),
    header_text: str = Form(default="", max_length=500),
    footer_text: str = Form(default="", max_length=500),
    is_default: bool = Form(default=False),
    logo: Optional[UploadFile] = File(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    template = ReportTemplate(
        name=name,
        company_name=company_name or None,
        primary_color=primary_color,
        secondary_color=secondary_color,
        header_text=header_text or None,
        footer_text=footer_text or None,
        is_default=is_default,
        created_by=current_user.id,
    )
    db.add(template)
    await db.flush()

    # Handle logo upload
    if logo and logo.filename:
        content = await logo.read()
        ext, _ = _validated_logo(logo, content)
        logo_dir = os.path.join(settings.data_dir, "templates", template.id)
        os.makedirs(logo_dir, exist_ok=True)
        logo_path = os.path.join(logo_dir, f"logo{ext}")

        with open(logo_path, "wb") as f:
            f.write(content)

        template.logo_path = logo_path
        await db.flush()

    # If set as default, unset other defaults
    if is_default:
        await _set_as_default(db, template.id)

    return _template_to_dict(template)


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    name: str = Form(..., min_length=1, max_length=120),
    company_name: str = Form(default="", max_length=120),
    primary_color: str = Form(default="#dc2626", pattern=r"^#[0-9A-Fa-f]{6}$"),
    secondary_color: str = Form(default="#1a1a25", pattern=r"^#[0-9A-Fa-f]{6}$"),
    header_text: str = Form(default="", max_length=500),
    footer_text: str = Form(default="", max_length=500),
    is_default: bool = Form(default=False),
    logo: Optional[UploadFile] = File(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(select(ReportTemplate).where(ReportTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.name = name
    template.company_name = company_name or None
    template.primary_color = primary_color
    template.secondary_color = secondary_color
    template.header_text = header_text or None
    template.footer_text = footer_text or None

    if logo and logo.filename:
        content = await logo.read()
        ext, _ = _validated_logo(logo, content)
        logo_dir = os.path.join(settings.data_dir, "templates", template.id)
        os.makedirs(logo_dir, exist_ok=True)
        logo_path = os.path.join(logo_dir, f"logo{ext}")
        previous_logo = template.logo_path
        with open(logo_path, "wb") as f:
            f.write(content)
        template.logo_path = logo_path
        if previous_logo and previous_logo != logo_path and os.path.exists(previous_logo):
            os.remove(previous_logo)

    if is_default:
        await _set_as_default(db, template.id)
    template.is_default = is_default

    await db.flush()
    return _template_to_dict(template)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(select(ReportTemplate).where(ReportTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Clean up logo
    if template.logo_path and os.path.exists(template.logo_path):
        import shutil
        logo_dir = os.path.dirname(template.logo_path)
        shutil.rmtree(logo_dir, ignore_errors=True)

    await db.delete(template)


@router.get("/{template_id}/logo")
async def get_template_logo(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ReportTemplate).where(ReportTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template or not template.logo_path or not os.path.exists(template.logo_path):
        raise HTTPException(status_code=404, detail="Logo not found")

    from fastapi.responses import FileResponse
    extension = os.path.splitext(template.logo_path)[1].lower()
    media_type = "image/png" if extension == ".png" else "image/jpeg"
    return FileResponse(
        template.logo_path,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


async def _set_as_default(db: AsyncSession, template_id: str):
    """Unset all other defaults."""
    result = await db.execute(select(ReportTemplate).where(ReportTemplate.is_default == True))
    for t in result.scalars().all():
        if t.id != template_id:
            t.is_default = False


def _template_to_dict(t: ReportTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "company_name": t.company_name,
        "has_logo": bool(t.logo_path),
        "primary_color": t.primary_color,
        "secondary_color": t.secondary_color,
        "header_text": t.header_text,
        "footer_text": t.footer_text,
        "is_default": t.is_default,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
