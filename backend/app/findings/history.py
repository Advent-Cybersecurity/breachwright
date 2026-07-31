"""Small, deterministic helpers for the local finding change trail."""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.engagements.models import Finding, FindingHistory


TRACKED_FIELDS = (
    "title",
    "description",
    "severity",
    "cvss_score",
    "affected_hosts",
    "evidence",
    "remediation",
    "retest_status",
    "retest_due_date",
    "source",
)


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def snapshot(finding: Finding) -> dict:
    return {field: _json_value(getattr(finding, field)) for field in TRACKED_FIELDS}


def diff(before: dict, after: dict) -> dict:
    return {
        field: {"from": before.get(field), "to": after.get(field)}
        for field in TRACKED_FIELDS
        if before.get(field) != after.get(field)
    }


async def record_history(
    db: AsyncSession,
    finding: Finding,
    *,
    action: str,
    created_by: str,
    changes: dict,
    source: str = "manual",
) -> FindingHistory | None:
    if not changes:
        return None
    entry = FindingHistory(
        finding_id=finding.id,
        engagement_id=finding.engagement_id,
        action=action,
        changes=changes,
        source=source,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    return entry
