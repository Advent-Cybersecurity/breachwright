"""Methodology Gap Detection: API Endpoints.

Provides scope-aware coverage analysis
by cross-referencing findings, checklists, and scan data against
OWASP/PTES/NIST methodologies using AI.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.gap_detection.service import analyze_gaps
from app.checklists.methodologies import get_available_methodologies

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements/{engagement_id}/gap-analysis", tags=["gap-analysis"])


@router.post("")
async def run_gap_analysis(
    engagement_id: str,
    methodology: str = Query("ptes", description="Methodology to review against: ptes, owasp_top10, nist_800_115, network_pentest"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Run AI-powered methodology gap detection.

    Analyzes the engagement's findings, checklist progress, and scan data
    against the selected methodology. The AI understands the engagement scope
    and only flags relevant gaps, not every checklist item.

    Returns:
      - engagement_type: inferred from scope and findings
      - gaps: list of missing/undertested areas with severity and recommendations
      - out_of_scope_items: methodology items intentionally excluded
      - coverage_score: 0-100 percentage
    """
    result = await analyze_gaps(db, engagement_id, methodology)

    if "error" in result:
        if result["error"] == "Engagement not found":
            raise HTTPException(status_code=404, detail=result["error"])
        if "AI provider" in result["error"]:
            raise HTTPException(status_code=502, detail=result["error"])
        if "Unknown methodology" in result["error"]:
            raise HTTPException(status_code=400, detail=result["error"])
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.get("/methodologies")
async def list_gap_methodologies(
    engagement_id: str,
    current_user: User = Depends(get_current_user),
):
    """List available methodologies for gap analysis."""
    return get_available_methodologies()
