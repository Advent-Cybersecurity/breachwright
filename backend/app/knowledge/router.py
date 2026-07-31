"""Cross-Engagement Intelligence — API Endpoints.

Cross-engagement intelligence that provides:
  - Knowledge base browsing and search
  - Cross-engagement trend analysis
  - Client risk profiles
  - AI-powered finding recommendations
  - Auto-indexing and manual reindexing
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_admin, require_editor
from app.auth.models import User
from app.knowledge.models import KnowledgeEntry, FindingKnowledgeLink
from app.knowledge.service import (
    index_engagement,
    get_trending_findings,
    get_finding_history,
    get_client_risk_profile,
    get_similar_environments,
    get_recommendations,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Browse & Search ─────────────────────────────────────────────────────────

@router.get("")
async def list_knowledge_entries(
    search: Optional[str] = Query(None, description="Search by title"),
    category: Optional[str] = Query(None, description="Filter by category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    sort: str = Query("occurrences", description="Sort by: occurrences, severity, recent"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Browse the knowledge base with search, filter, and sort."""
    query = select(KnowledgeEntry)

    if search:
        query = query.where(
            or_(
                KnowledgeEntry.canonical_title.ilike(f"%{search}%"),
                KnowledgeEntry.description.ilike(f"%{search}%"),
            )
        )
    if category:
        query = query.where(KnowledgeEntry.category == category)
    if severity:
        query = query.where(KnowledgeEntry.default_severity == severity)

    # Sort
    if sort == "severity":
        # Can't sort by enum order easily, sort by CVSS desc as proxy
        query = query.order_by(KnowledgeEntry.default_cvss.desc().nullslast())
    elif sort == "recent":
        query = query.order_by(KnowledgeEntry.last_seen_at.desc().nullslast())
    else:  # occurrences (default)
        query = query.order_by(KnowledgeEntry.occurrence_count.desc())

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Paginate
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    entries = result.scalars().all()

    return {
        "total": total,
        "entries": [
            {
                "id": e.id,
                "canonical_title": e.canonical_title,
                "category": e.category.value if hasattr(e.category, 'value') else e.category,
                "description": (e.description or "")[:200],
                "default_severity": e.default_severity,
                "default_cvss": e.default_cvss,
                "cwe_id": e.cwe_id,
                "mitre_attack_id": e.mitre_attack_id,
                "occurrence_count": e.occurrence_count,
                "unique_client_count": e.unique_client_count,
                "last_seen_at": e.last_seen_at.isoformat() if e.last_seen_at else None,
                "tags": e.tags or [],
            }
            for e in entries
        ],
    }


@router.get("/stats")
async def knowledge_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """High-level stats for the knowledge base dashboard."""
    total_entries = (await db.execute(
        select(func.count(KnowledgeEntry.id))
    )).scalar_one()

    total_links = (await db.execute(
        select(func.count(FindingKnowledgeLink.id))
    )).scalar_one()

    unique_clients = (await db.execute(
        select(func.count(func.distinct(FindingKnowledgeLink.client_name)))
    )).scalar_one()

    unique_engagements = (await db.execute(
        select(func.count(func.distinct(FindingKnowledgeLink.engagement_id)))
    )).scalar_one()

    # Category breakdown
    cat_result = await db.execute(
        select(
            KnowledgeEntry.category,
            func.count(KnowledgeEntry.id),
        ).group_by(KnowledgeEntry.category)
    )
    categories = {
        (r[0].value if hasattr(r[0], 'value') else r[0]): r[1]
        for r in cat_result.all()
    }

    # Severity breakdown
    sev_result = await db.execute(
        select(
            KnowledgeEntry.default_severity,
            func.count(KnowledgeEntry.id),
        ).group_by(KnowledgeEntry.default_severity)
    )
    severities = {r[0] or "unknown": r[1] for r in sev_result.all()}

    return {
        "total_finding_types": total_entries,
        "total_occurrences": total_links,
        "unique_clients": unique_clients,
        "indexed_engagements": unique_engagements,
        "by_category": categories,
        "by_severity": severities,
    }


# ── Trending ────────────────────────────────────────────────────────────────

@router.get("/trending")
async def trending_findings(
    category: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the most common finding types across all engagements."""
    return await get_trending_findings(db, limit=limit, category=category)


# ── Finding Deep Dive ───────────────────────────────────────────────────────

@router.get("/entries/{entry_id}")
async def knowledge_entry_detail(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full detail on a knowledge entry, including every engagement it appeared in."""
    history = await get_finding_history(db, entry_id)
    if not history:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    return history


@router.patch("/entries/{entry_id}")
async def update_knowledge_entry(
    entry_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Manually update a knowledge entry (title, description, CWE, MITRE, tags)."""
    result = await db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")

    allowed_fields = {
        "canonical_title", "description", "remediation",
        "cwe_id", "mitre_attack_id", "tags", "category",
        "default_severity", "default_cvss",
    }
    for key, value in body.items():
        if key in allowed_fields:
            setattr(entry, key, value)

    await db.flush()
    return {"status": "updated", "id": entry.id}


# ── Client Risk Profile ────────────────────────────────────────────────────

@router.get("/clients")
async def list_clients(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all clients with their engagement/finding counts."""
    result = await db.execute(
        select(
            FindingKnowledgeLink.client_name,
            func.count(func.distinct(FindingKnowledgeLink.engagement_id)).label("engagements"),
            func.count(func.distinct(FindingKnowledgeLink.knowledge_entry_id)).label("finding_types"),
            func.count(FindingKnowledgeLink.id).label("total_findings"),
        ).group_by(FindingKnowledgeLink.client_name)
        .order_by(func.count(FindingKnowledgeLink.id).desc())
    )

    return [
        {
            "client_name": r[0],
            "engagement_count": r[1],
            "unique_finding_types": r[2],
            "total_findings": r[3],
        }
        for r in result.all()
    ]


@router.get("/clients/{client_name}/profile")
async def client_risk_profile(
    client_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full risk profile for a client across all their engagements."""
    profile = await get_client_risk_profile(db, client_name)
    if profile.get("engagements") == 0:
        raise HTTPException(status_code=404, detail="No data for this client")
    return profile


# ── Recommendations ─────────────────────────────────────────────────────────

@router.get("/engagements/{engagement_id}/similar")
async def similar_engagements(
    engagement_id: str,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Find engagements with similar finding profiles (Jaccard similarity)."""
    return await get_similar_environments(db, engagement_id, limit=limit)


@router.get("/engagements/{engagement_id}/recommendations")
async def engagement_recommendations(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recommend findings to look for based on similar engagements.

    "Clients with similar environments also had these findings, but
    you haven't reported them yet."
    """
    recs = await get_recommendations(db, engagement_id)
    return {
        "engagement_id": engagement_id,
        "recommendations": recs,
        "note": "Based on similarity analysis with past engagements",
    }


# ── Indexing ────────────────────────────────────────────────────────────────

@router.post("/index/{engagement_id}")
async def index_engagement_endpoint(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Index (or re-index) all findings from an engagement into the knowledge base."""
    result = await index_engagement(db, engagement_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/index-all")
async def index_all_engagements(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Rebuild the entire knowledge base from all engagements. Admin only."""
    from app.engagements.models import Engagement

    result = await db.execute(select(Engagement.id))
    engagement_ids = [r[0] for r in result.all()]

    total_stats = {"engagements": 0, "indexed": 0, "new_entries": 0, "existing_entries": 0}

    for eid in engagement_ids:
        stats = await index_engagement(db, eid)
        if "error" not in stats:
            total_stats["engagements"] += 1
            total_stats["indexed"] += stats["indexed"]
            total_stats["new_entries"] += stats["new_entries"]
            total_stats["existing_entries"] += stats["existing_entries"]

    logger.info("Full reindex complete: %s", total_stats)
    return total_stats
