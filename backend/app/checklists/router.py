import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.checklists.models import ChecklistItem
from app.checklists.methodologies import get_methodology_items, get_available_methodologies
from app.engagements.models import Engagement

logger = logging.getLogger(__name__)

router = APIRouter(tags=["checklists"])


class ChecklistStatusUpdate(BaseModel):
    status: str  # pending, in_progress, done, na
    notes: Optional[str] = None


@router.get("/api/methodologies")
async def list_methodologies(current_user: User = Depends(get_current_user)):
    """List available methodology templates."""
    return get_available_methodologies()


@router.get("/api/engagements/{engagement_id}/checklists")
async def get_checklists(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all checklist items for an engagement."""
    result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.engagement_id == engagement_id)
        .order_by(ChecklistItem.methodology, ChecklistItem.order_index)
    )
    items = result.scalars().all()
    return [
        {
            "id": i.id,
            "methodology": i.methodology,
            "category": i.category,
            "item": i.item,
            "description": i.description,
            "tools": i.tools,
            "techniques": i.techniques,
            "reference_url": i.reference_url,
            "status": i.status,
            "notes": i.notes,
            "order_index": i.order_index,
        }
        for i in items
    ]


@router.post("/api/engagements/{engagement_id}/checklists/{methodology}")
async def populate_checklist(
    engagement_id: str,
    methodology: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Populate an engagement with a methodology checklist."""
    engagement_result = await db.execute(
        select(Engagement.id).where(Engagement.id == engagement_id)
    )
    if not engagement_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
    items = get_methodology_items(methodology)
    if not items:
        raise HTTPException(status_code=404, detail=f"Methodology '{methodology}' not found")

    # Check if already populated for this methodology
    existing = await db.execute(
        select(func.count(ChecklistItem.id))
        .where(ChecklistItem.engagement_id == engagement_id, ChecklistItem.methodology == methodology)
    )
    if existing.scalar_one() > 0:
        raise HTTPException(status_code=409, detail=f"Checklist for '{methodology}' already exists. Clear it first.")

    created = []
    for item_data in items:
        item = ChecklistItem(
            engagement_id=engagement_id,
            methodology=methodology,
            category=item_data["category"],
            item=item_data["item"],
            description=item_data.get("description"),
            tools=item_data.get("tools"),
            techniques=item_data.get("techniques"),
            reference_url=item_data.get("reference_url"),
            order_index=item_data.get("order_index", 0),
        )
        db.add(item)
        created.append(item)

    await db.flush()

    logger.info("Populated %d checklist items for %s on engagement %s", len(created), methodology, engagement_id)

    return {
        "methodology": methodology,
        "items_created": len(created),
    }


@router.put("/api/engagements/{engagement_id}/checklists/{item_id}")
async def update_checklist_item(
    engagement_id: str,
    item_id: str,
    body: ChecklistStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Update a checklist item's status and notes."""
    result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.id == item_id, ChecklistItem.engagement_id == engagement_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    if body.status not in ("pending", "in_progress", "done", "na"):
        raise HTTPException(status_code=400, detail="Invalid status")

    item.status = body.status
    if body.notes is not None:
        item.notes = body.notes
    item.updated_by = current_user.id
    item.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "id": item.id,
        "status": item.status,
        "notes": item.notes,
    }


@router.delete("/api/engagements/{engagement_id}/checklists/{methodology}")
async def clear_checklist(
    engagement_id: str,
    methodology: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Clear all checklist items for a methodology on an engagement."""
    await db.execute(
        delete(ChecklistItem)
        .where(ChecklistItem.engagement_id == engagement_id, ChecklistItem.methodology == methodology)
    )
    return {"status": "cleared"}


@router.get("/api/engagements/{engagement_id}/checklists/progress")
async def get_checklist_progress(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get progress summary for all checklists on an engagement."""
    result = await db.execute(
        select(
            ChecklistItem.methodology,
            ChecklistItem.status,
            func.count(ChecklistItem.id),
        )
        .where(ChecklistItem.engagement_id == engagement_id)
        .group_by(ChecklistItem.methodology, ChecklistItem.status)
    )

    progress = {}
    for methodology, status, count in result.all():
        if methodology not in progress:
            progress[methodology] = {"total": 0, "done": 0, "in_progress": 0, "pending": 0, "na": 0}
        progress[methodology][status] = count
        progress[methodology]["total"] += count

    return progress
