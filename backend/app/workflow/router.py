"""Repeatable assessment, readiness, retest, and interoperability endpoints."""

import hashlib
import ipaddress
import json
import re
import csv
from io import StringIO
from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import String, case, cast, select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.checklists.models import ChecklistItem
from app.db.session import get_db
from app.engagements.models import (
    AIFindingDraft,
    AttackPath,
    AssessmentTemplate,
    Engagement,
    EvidenceAttachment,
    EvidenceNote,
    EvidenceNoteAttachment,
    Finding,
    Report,
    ScanObservation,
    ScanSnapshot,
    ScanUpload,
)
from app.correlation.engine import correlate
from app.correlation.structured_parsers import parse_structured
from app.ai.context import redact_sensitive_text
from app.engagements.schemas import FindingResponse
from app.findings.history import record_history, snapshot as finding_snapshot
from app.workflow.templates import ENGAGEMENT_TEMPLATES


router = APIRouter(prefix="/api/engagements/{engagement_id}", tags=["workflow"])
SNAPSHOT_PARSER_VERSION = "structured-v2"
MAX_SNAPSHOT_SCANS = 50
MAX_SNAPSHOT_BYTES = 250 * 1024 * 1024
MAX_COMPARISON_DETAILS_PER_STATUS = 500
MAX_ASSET_INVENTORY_ITEMS = 500
MAX_ASSET_OBSERVATIONS_PER_TYPE = 100
MAX_ASSET_FINDINGS_PER_HOST = 100
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class SnapshotCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    scan_ids: list[
        Annotated[str, Field(min_length=36, max_length=36)]
    ] = Field(min_length=1, max_length=MAX_SNAPSHOT_SCANS)

    model_config = {"str_strip_whitespace": True}


def _severity_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _normalize_component(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _normalize_host(value) -> str:
    """Return a conservative host identity for linking scanner and finding data."""
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    host = parsed.hostname
    if not host:
        host = candidate.split("/", 1)[0].strip().strip("[]")
        if host.count(":") == 1:
            name, possible_port = host.rsplit(":", 1)
            if possible_port.isdigit():
                host = name
    host = host.strip().rstrip(".").lower()
    try:
        return ipaddress.ip_address(host).compressed
    except ValueError:
        return host


def _finding_hosts(finding: Finding) -> set[str]:
    values = re.split(r"[,;\n]+", finding.affected_hosts or "")
    for ref in finding.evidence_refs or []:
        if not isinstance(ref, dict):
            continue
        for key in ("host", "hostname", "target", "url", "uri", "matched_at", "matched-at"):
            if ref.get(key):
                values.append(str(ref[key]))
    return {host for value in values if (host := _normalize_host(value))}


def _search_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _search_snippet(query: str, *values, limit: int = 240) -> str:
    query_lower = query.lower()
    for value in values:
        compact = re.sub(r"\s+", " ", str(value or "")).strip()
        if not compact:
            continue
        match_at = compact.lower().find(query_lower)
        if match_at < 0:
            continue
        start = max(0, match_at - 70)
        end = min(len(compact), start + limit)
        prefix = "..." if start else ""
        suffix = "..." if end < len(compact) else ""
        return f"{prefix}{compact[start:end]}{suffix}"
    return ""


def _observation_evidence_search_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    parts = []
    for key in ("cve", "service", "product", "version", "protocol", "operating_system"):
        if value.get(key):
            parts.append(str(value[key]))
    parts.extend(str(item) for item in (value.get("hostnames") or []) if item)
    for ref in value.get("evidence_refs") or []:
        if not isinstance(ref, dict):
            continue
        for key in ("filename", "scan_type", "tool", "host", "cve", "plugin_id", "excerpt"):
            if ref.get(key):
                parts.append(str(ref[key]))
    return " · ".join(dict.fromkeys(parts))[:5000]


def _fingerprint(*, cve, title, host, port) -> str:
    identity = _normalize_component(cve) or _normalize_component(title)
    material = json.dumps(
        [identity, _normalize_component(host), int(port) if port is not None else None],
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _read_snapshot_payload(file_path: str, filename: str, remaining: int) -> bytes:
    try:
        with open(file_path, "rb") as handle:
            payload = handle.read(remaining + 1)
    except FileNotFoundError:
        raise HTTPException(status_code=409, detail=f"Stored file is missing for {filename}")
    except OSError as exc:
        raise HTTPException(status_code=409, detail=f"Stored file could not be read for {filename}") from exc
    if len(payload) > remaining:
        raise HTTPException(
            status_code=413,
            detail=f"Selected scans exceed the {MAX_SNAPSHOT_BYTES // (1024 * 1024)} MB snapshot limit",
        )
    return payload


async def _require_engagement(db: AsyncSession, engagement_id: str) -> Engagement:
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return engagement


def _snapshot_response(snapshot: ScanSnapshot) -> dict:
    return {
        "id": snapshot.id,
        "label": snapshot.label,
        "source_scan_ids": snapshot.source_scan_ids,
        "parser_version": snapshot.parser_version,
        "observation_count": snapshot.observation_count,
        "created_at": snapshot.created_at,
    }


async def _snapshot_observations(db: AsyncSession, snapshot_id: str) -> dict[str, ScanObservation]:
    result = await db.execute(
        select(ScanObservation).where(ScanObservation.snapshot_id == snapshot_id)
    )
    return {item.fingerprint: item for item in result.scalars().all()}


def _observation_response(item: ScanObservation, status: str) -> dict:
    return {
        "status": status,
        "fingerprint": item.fingerprint,
        "tool": item.tool,
        "title": item.title,
        "severity": item.severity,
        "host": item.host,
        "port": item.port,
        "evidence_ref": item.evidence_ref,
    }


def _limited_keys(keys: set[str]) -> tuple[list[str], int]:
    ordered = sorted(keys)
    return (
        ordered[:MAX_COMPARISON_DETAILS_PER_STATUS],
        max(0, len(ordered) - MAX_COMPARISON_DETAILS_PER_STATUS),
    )


async def _comparison(db: AsyncSession, engagement_id: str, current: ScanSnapshot) -> dict:
    prior, previous, current_items, previous_items, older_fingerprints = (
        await _comparison_material(db, engagement_id, current)
    )

    current_keys = set(current_items)
    previous_keys = set(previous_items)
    persistent_keys = current_keys & previous_keys
    resolved_keys = previous_keys - current_keys
    appeared_keys = current_keys - previous_keys
    regressed_keys = appeared_keys & older_fingerprints
    new_keys = appeared_keys - regressed_keys
    warnings = []
    if previous and previous.parser_version != current.parser_version:
        warnings.append({
            "code": "mixed_snapshot_parsers",
            "message": (
                "These snapshots use different normalization versions. "
                "Treat the comparison as advisory and create a new baseline."
            ),
        })

    detail_keys = {}
    truncated = {}
    for status, keys in (
        ("new", new_keys),
        ("persistent", persistent_keys),
        ("resolved", resolved_keys),
        ("regressed", regressed_keys),
    ):
        detail_keys[status], truncated[status] = _limited_keys(keys)

    def current_rows(status):
        return [
            _observation_response(current_items[key], status)
            for key in detail_keys[status]
        ]

    return {
        "snapshot": _snapshot_response(current),
        "baseline": _snapshot_response(previous) if previous else None,
        "counts": {
            "new": len(new_keys),
            "persistent": len(persistent_keys),
            "resolved": len(resolved_keys),
            "regressed": len(regressed_keys),
        },
        "new": current_rows("new"),
        "persistent": current_rows("persistent"),
        "resolved": [
            _observation_response(previous_items[key], "resolved")
            for key in detail_keys["resolved"]
        ],
        "regressed": current_rows("regressed"),
        "warnings": warnings,
        "detail_summary": {
            "limit_per_status": MAX_COMPARISON_DETAILS_PER_STATUS,
            "truncated": truncated,
        },
    }


async def _comparison_material(
    db: AsyncSession,
    engagement_id: str,
    current: ScanSnapshot,
) -> tuple[list[ScanSnapshot], ScanSnapshot | None, dict, dict, set[str]]:
    prior_result = await db.execute(
        select(ScanSnapshot)
        .where(
            ScanSnapshot.engagement_id == engagement_id,
            ScanSnapshot.id != current.id,
            ScanSnapshot.created_at <= current.created_at,
        )
        .order_by(ScanSnapshot.created_at.desc(), ScanSnapshot.id.desc())
    )
    prior = prior_result.scalars().all()
    previous = prior[0] if prior else None
    current_items = await _snapshot_observations(db, current.id)
    previous_items = await _snapshot_observations(db, previous.id) if previous else {}
    older_fingerprints: set[str] = set()
    older_snapshot_ids = [snapshot.id for snapshot in prior[1:]]
    for offset in range(0, len(older_snapshot_ids), 500):
        batch = older_snapshot_ids[offset:offset + 500]
        older_fingerprints.update((await db.execute(
            select(ScanObservation.fingerprint)
            .where(ScanObservation.snapshot_id.in_(batch))
            .distinct()
        )).scalars().all())

    return prior, previous, current_items, previous_items, older_fingerprints


@router.get("/workflow/templates")
async def list_templates(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_engagement(db, engagement_id)
    user_templates = list((await db.execute(
        select(AssessmentTemplate).order_by(AssessmentTemplate.name, AssessmentTemplate.key)
    )).scalars().all())
    return [
        *[{"key": key, **value, "built_in": True, "schema_version": 1} for key, value in ENGAGEMENT_TEMPLATES.items()],
        *[
            {
                "key": template.key,
                "name": template.name,
                "description": template.description,
                "methodologies": template.methodologies,
                "built_in": False,
                "schema_version": template.schema_version,
            }
            for template in user_templates
        ],
    ]


@router.get("/retest-queue")
async def retest_queue(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_engagement(db, engagement_id)
    result = await db.execute(
        select(Finding)
        .where(
            Finding.engagement_id == engagement_id,
            Finding.retest_status.in_(["open", "retest_needed"]),
        )
        .order_by(
            Finding.retest_due_date.is_(None),
            Finding.retest_due_date,
            case(
                (Finding.severity == "critical", 0),
                (Finding.severity == "high", 1),
                (Finding.severity == "medium", 2),
                (Finding.severity == "low", 3),
                else_=4,
            ),
            Finding.created_at,
            Finding.id,
        )
    )
    today = date.today()
    return [
        {
            "id": finding.id,
            "title": finding.title,
            "severity": _severity_value(finding.severity),
            "retest_status": finding.retest_status,
            "retest_due_date": finding.retest_due_date,
            "overdue": bool(finding.retest_due_date and finding.retest_due_date < today),
        }
        for finding in result.scalars().all()
    ]


@router.get("/retest-overview")
async def retest_overview(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_engagement(db, engagement_id)
    findings = list((await db.execute(
        select(Finding)
        .where(
            Finding.engagement_id == engagement_id,
            Finding.retest_status.isnot(None),
        )
        .order_by(
            case(*[(Finding.severity == severity, rank) for severity, rank in SEVERITY_RANK.items()], else_=5),
            Finding.retest_due_date.is_(None),
            Finding.retest_due_date,
            Finding.id,
        )
    )).scalars().all())
    today = date.today()
    due_soon_cutoff = today + timedelta(days=7)
    recently_resolved_cutoff = today - timedelta(days=30)
    groups = {
        "overdue": [],
        "due_soon": [],
        "scheduled": [],
        "unscheduled": [],
        "recently_resolved": [],
    }

    def response(finding: Finding) -> dict:
        return {
            "id": finding.id,
            "title": finding.title,
            "severity": _severity_value(finding.severity),
            "affected_hosts": finding.affected_hosts,
            "retest_status": finding.retest_status,
            "retest_due_date": finding.retest_due_date,
            "updated_at": finding.updated_at,
        }

    accepted_risk = 0
    for finding in findings:
        if finding.retest_status == "accepted_risk":
            accepted_risk += 1
            continue
        if finding.retest_status == "remediated":
            updated_date = finding.updated_at.date() if finding.updated_at else today
            if updated_date >= recently_resolved_cutoff:
                groups["recently_resolved"].append(response(finding))
            continue
        if finding.retest_status not in {"open", "retest_needed"}:
            continue
        if finding.retest_due_date is None:
            groups["unscheduled"].append(response(finding))
        elif finding.retest_due_date < today:
            groups["overdue"].append(response(finding))
        elif finding.retest_due_date <= due_soon_cutoff:
            groups["due_soon"].append(response(finding))
        else:
            groups["scheduled"].append(response(finding))

    return {
        "as_of": today,
        "due_soon_days": 7,
        "recently_resolved_days": 30,
        "summary": {
            **{key: len(items) for key, items in groups.items()},
            "accepted_risk": accepted_risk,
        },
        **groups,
    }


@router.get("/report-readiness")
async def report_readiness(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    engagement = await _require_engagement(db, engagement_id)
    findings = list((await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .order_by(Finding.created_at, Finding.id)
    )).scalars().all())
    finding_ids = [finding.id for finding in findings]
    attachment_finding_ids = (
        set((await db.execute(
            select(EvidenceAttachment.finding_id).where(
                EvidenceAttachment.finding_id.in_(finding_ids)
            )
        )).scalars().all())
        if finding_ids
        else set()
    )
    checklist_counts = dict(
        (await db.execute(
            select(ChecklistItem.status, func.count(ChecklistItem.id))
            .where(ChecklistItem.engagement_id == engagement_id)
            .group_by(ChecklistItem.status)
        )).all()
    )
    pending_drafts = int((await db.execute(
        select(func.count(AIFindingDraft.id)).where(
            AIFindingDraft.engagement_id == engagement_id,
            AIFindingDraft.status == "pending",
        )
    )).scalar_one())
    snapshots = list((await db.execute(
        select(ScanSnapshot)
        .where(ScanSnapshot.engagement_id == engagement_id)
        .order_by(ScanSnapshot.created_at.desc(), ScanSnapshot.id.desc())
    )).scalars().all())
    snapshot_count = len(snapshots)
    unversioned_scan_count = 0
    if snapshots:
        scan_ids = set((await db.execute(
            select(ScanUpload.id).where(
            ScanUpload.engagement_id == engagement_id
            )
        )).scalars().all())
        versioned_scan_ids = {
            scan_id
            for snapshot_item in snapshots
            for scan_id in (snapshot_item.source_scan_ids or [])
        }
        unversioned_scan_count = len(scan_ids - versioned_scan_ids)

    missing_evidence = [
        f for f in findings
        if _severity_value(f.severity) in {"critical", "high"}
        and not (f.evidence or f.evidence_refs or f.id in attachment_finding_ids)
    ]
    missing_remediation = [f for f in findings if _severity_value(f.severity) in {"critical", "high"} and not f.remediation]
    unresolved = [f for f in findings if f.retest_status in {"open", "retest_needed"}]
    note_ids = set((await db.execute(
        select(EvidenceNote.id).where(EvidenceNote.engagement_id == engagement_id)
    )).scalars().all())
    reviewed_note_ids = {
        ref.get("evidence_note_id")
        for finding in findings
        for ref in (finding.evidence_refs or [])
        if isinstance(ref, dict) and ref.get("evidence_note_id")
    }
    unreviewed_note_count = len(note_ids - reviewed_note_ids)
    blockers = []
    if missing_evidence:
        blockers.append({"code": "high_risk_missing_evidence", "message": f"{len(missing_evidence)} critical or high finding(s) lack evidence.", "finding_ids": [f.id for f in missing_evidence]})
    if missing_remediation:
        blockers.append({"code": "high_risk_missing_remediation", "message": f"{len(missing_remediation)} critical or high finding(s) lack remediation.", "finding_ids": [f.id for f in missing_remediation]})
    warnings = []
    if not findings:
        warnings.append({"code": "no_findings", "message": "The engagement has no accepted findings."})
    if not engagement.scope:
        warnings.append({"code": "missing_scope", "message": "The engagement scope is empty."})
    incomplete = checklist_counts.get("pending", 0) + checklist_counts.get("in_progress", 0)
    if incomplete:
        warnings.append({"code": "incomplete_checklist", "message": f"{incomplete} checklist item(s) remain incomplete."})
    if unresolved:
        warnings.append({"code": "unresolved_retests", "message": f"{len(unresolved)} finding(s) remain in the retest queue."})
    if pending_drafts:
        warnings.append({"code": "pending_ai_drafts", "message": f"{pending_drafts} AI proposal(s) still require review."})
    if unreviewed_note_count:
        warnings.append({
            "code": "unreviewed_evidence_notes",
            "message": f"{unreviewed_note_count} evidence notebook note(s) have not been promoted to a finding.",
        })
    if not snapshot_count:
        warnings.append({"code": "no_scan_snapshot", "message": "No versioned scan snapshot has been created."})
    else:
        if (
            len(snapshots) > 1
            and snapshots[0].parser_version != snapshots[1].parser_version
        ):
            warnings.append({
                "code": "mixed_snapshot_parsers",
                "message": (
                    "The latest comparison spans different normalization "
                    "versions. Create a new baseline before relying on it."
                ),
            })
        elif snapshots[0].parser_version != SNAPSHOT_PARSER_VERSION:
            warnings.append({
                "code": "outdated_snapshot_parser",
                "message": (
                    "The latest snapshot uses an older normalization version. "
                    "Create a new snapshot before relying on comparison results."
                ),
            })
        if unversioned_scan_count:
            warnings.append({
                "code": "unversioned_scans",
                "message": (
                    f"{unversioned_scan_count} scan upload(s) are not included "
                    "in any versioned snapshot."
                ),
            })
    score = max(0, 100 - 25 * len(blockers) - 5 * len(warnings))
    return {
        "ready": not blockers,
        "score": score,
        "blockers": blockers,
        "warnings": warnings,
        "summary": {
            "findings": len(findings),
            "pending_ai_drafts": pending_drafts,
            "unreviewed_evidence_notes": unreviewed_note_count,
            "unresolved_retests": len(unresolved),
            "checklist_incomplete": incomplete,
            "scan_snapshots": snapshot_count,
            "unversioned_scans": unversioned_scan_count,
        },
    }


@router.get("/scan-snapshots")
async def list_snapshots(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_engagement(db, engagement_id)
    result = await db.execute(
        select(ScanSnapshot)
        .where(ScanSnapshot.engagement_id == engagement_id)
        .order_by(ScanSnapshot.created_at.desc(), ScanSnapshot.id.desc())
    )
    return [_snapshot_response(snapshot) for snapshot in result.scalars().all()]


@router.get("/activity")
async def recent_activity(
    engagement_id: str,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a bounded local activity view reconstructed from durable records."""
    await _require_engagement(db, engagement_id)
    per_type = min(limit, 20)
    findings = (await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .order_by(Finding.updated_at.desc(), Finding.id.desc())
        .limit(per_type)
    )).scalars().all()
    notes = (await db.execute(
        select(EvidenceNote)
        .where(EvidenceNote.engagement_id == engagement_id)
        .order_by(EvidenceNote.updated_at.desc(), EvidenceNote.id.desc())
        .limit(per_type)
    )).scalars().all()
    scans = (await db.execute(
        select(ScanUpload)
        .where(ScanUpload.engagement_id == engagement_id)
        .order_by(ScanUpload.created_at.desc(), ScanUpload.id.desc())
        .limit(per_type)
    )).scalars().all()
    snapshots = (await db.execute(
        select(ScanSnapshot)
        .where(ScanSnapshot.engagement_id == engagement_id)
        .order_by(ScanSnapshot.created_at.desc(), ScanSnapshot.id.desc())
        .limit(per_type)
    )).scalars().all()
    reports = (await db.execute(
        select(Report)
        .where(Report.engagement_id == engagement_id)
        .order_by(Report.created_at.desc(), Report.id.desc())
        .limit(per_type)
    )).scalars().all()

    events = [
        {
            "kind": "finding",
            "id": finding.id,
            "title": finding.title,
            "detail": f"{_severity_value(finding.severity).title()} finding activity",
            "timestamp": finding.updated_at or finding.created_at,
            "tab": "findings",
        }
        for finding in findings
    ]
    events.extend({
        "kind": "evidence_note",
        "id": note.id,
        "title": note.title,
        "detail": "Evidence Notebook activity",
        "timestamp": note.updated_at or note.created_at,
        "tab": "notebook",
    } for note in notes)
    events.extend({
        "kind": "scan",
        "id": scan.id,
        "title": scan.filename,
        "detail": f"{scan.scan_type.upper()} scan added",
        "timestamp": scan.created_at,
        "tab": "scans",
    } for scan in scans)
    events.extend({
        "kind": "snapshot",
        "id": snapshot.id,
        "title": snapshot.label,
        "detail": f"Snapshot with {snapshot.observation_count} observations",
        "timestamp": snapshot.created_at,
        "tab": "scans",
    } for snapshot in snapshots)
    events.extend({
        "kind": "report",
        "id": report.id,
        "title": report.title,
        "detail": f"{report.format.upper()} report generated",
        "timestamp": report.created_at,
        "tab": "reports",
    } for report in reports)

    def sort_key(event):
        value = event["timestamp"]
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (value, event["kind"], event["id"])

    events.sort(key=sort_key, reverse=True)
    return {
        "count": min(len(events), limit),
        "limit": limit,
        "events": events[:limit],
    }


@router.get("/search")
async def search_workspace(
    engagement_id: str,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search engagement records locally without indexing or external services."""
    engagement = await _require_engagement(db, engagement_id)
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(status_code=422, detail="Search text must contain at least 2 characters")
    pattern = _search_pattern(query)
    per_type = min(limit, 50)
    results = []

    engagement_values = (engagement.name, engagement.client_name, engagement.scope)
    if any(query.lower() in str(value or "").lower() for value in engagement_values):
        results.append({
            "type": "engagement",
            "id": engagement.id,
            "title": engagement.name,
            "subtitle": engagement.client_name,
            "snippet": _search_snippet(query, *engagement_values),
            "tab": "findings",
        })

    finding_rows = (await db.execute(
        select(Finding)
        .where(
            Finding.engagement_id == engagement_id,
            or_(
                Finding.title.ilike(pattern, escape="\\"),
                Finding.description.ilike(pattern, escape="\\"),
                Finding.affected_hosts.ilike(pattern, escape="\\"),
                Finding.evidence.ilike(pattern, escape="\\"),
                Finding.remediation.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(
            case(*[(Finding.severity == severity, rank) for severity, rank in SEVERITY_RANK.items()], else_=5),
            Finding.created_at,
            Finding.id,
        )
        .limit(per_type)
    )).scalars().all()
    results.extend({
        "type": "finding",
        "id": finding.id,
        "title": finding.title,
        "subtitle": f"{_severity_value(finding.severity).title()} finding",
        "snippet": _search_snippet(
            query,
            finding.title,
            finding.affected_hosts,
            finding.description,
            finding.evidence,
            finding.remediation,
        ),
        "tab": "findings",
    } for finding in finding_rows)

    checklist_rows = (await db.execute(
        select(ChecklistItem)
        .where(
            ChecklistItem.engagement_id == engagement_id,
            or_(
                ChecklistItem.item.ilike(pattern, escape="\\"),
                ChecklistItem.category.ilike(pattern, escape="\\"),
                ChecklistItem.description.ilike(pattern, escape="\\"),
                ChecklistItem.tools.ilike(pattern, escape="\\"),
                ChecklistItem.techniques.ilike(pattern, escape="\\"),
                ChecklistItem.notes.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(ChecklistItem.order_index, ChecklistItem.id)
        .limit(per_type)
    )).scalars().all()
    results.extend({
        "type": "checklist",
        "id": item.id,
        "title": item.item,
        "subtitle": f"{item.category} · {item.status.replace('_', ' ')}",
        "snippet": _search_snippet(
            query,
            item.item,
            item.category,
            item.description,
            item.tools,
            item.techniques,
            item.notes,
        ),
        "tab": "checklists",
    } for item in checklist_rows)

    evidence_rows = (await db.execute(
        select(EvidenceAttachment, Finding.title, Finding.id)
        .join(Finding, Finding.id == EvidenceAttachment.finding_id)
        .where(
            Finding.engagement_id == engagement_id,
            or_(
                EvidenceAttachment.filename.ilike(pattern, escape="\\"),
                EvidenceAttachment.content_type.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(EvidenceAttachment.created_at.desc(), EvidenceAttachment.id)
        .limit(per_type)
    )).all()
    results.extend({
        "type": "evidence",
        "id": attachment.id,
        "title": attachment.filename,
        "subtitle": f"Evidence for {finding_title}",
        "snippet": _search_snippet(query, attachment.filename, attachment.content_type),
        "tab": "findings",
        "finding_id": finding_id,
    } for attachment, finding_title, finding_id in evidence_rows)

    note_rows = (await db.execute(
        select(EvidenceNote)
        .where(
            EvidenceNote.engagement_id == engagement_id,
            or_(
                EvidenceNote.title.ilike(pattern, escape="\\"),
                EvidenceNote.body.ilike(pattern, escape="\\"),
                EvidenceNote.asset.ilike(pattern, escape="\\"),
                cast(EvidenceNote.tags, String).ilike(pattern, escape="\\"),
            ),
        )
        .order_by(EvidenceNote.updated_at.desc(), EvidenceNote.id)
        .limit(per_type)
    )).scalars().all()
    results.extend({
        "type": "notebook note",
        "id": note.id,
        "title": note.title,
        "subtitle": note.asset or "Evidence notebook",
        "snippet": _search_snippet(query, note.title, note.asset, *(note.tags or []), note.body),
        "tab": "notebook",
    } for note in note_rows)

    note_attachment_rows = (await db.execute(
        select(EvidenceNoteAttachment, EvidenceNote.title)
        .join(EvidenceNote, EvidenceNote.id == EvidenceNoteAttachment.note_id)
        .where(
            EvidenceNote.engagement_id == engagement_id,
            or_(
                EvidenceNoteAttachment.filename.ilike(pattern, escape="\\"),
                EvidenceNoteAttachment.content_type.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(EvidenceNoteAttachment.created_at.desc(), EvidenceNoteAttachment.id)
        .limit(per_type)
    )).all()
    results.extend({
        "type": "notebook attachment",
        "id": attachment.id,
        "title": attachment.filename,
        "subtitle": f"Attached to {note_title}",
        "snippet": _search_snippet(query, attachment.filename, attachment.content_type),
        "tab": "notebook",
    } for attachment, note_title in note_attachment_rows)

    latest_snapshot = (await db.execute(
        select(ScanSnapshot)
        .where(ScanSnapshot.engagement_id == engagement_id)
        .order_by(ScanSnapshot.created_at.desc(), ScanSnapshot.id.desc())
        .limit(1)
    )).scalar_one_or_none()
    if latest_snapshot:
        observation_rows = (await db.execute(
            select(ScanObservation)
            .where(
                ScanObservation.snapshot_id == latest_snapshot.id,
                or_(
                    ScanObservation.host.ilike(pattern, escape="\\"),
                    ScanObservation.title.ilike(pattern, escape="\\"),
                    ScanObservation.tool.ilike(pattern, escape="\\"),
                    cast(ScanObservation.evidence_ref, String).ilike(pattern, escape="\\"),
                ),
            )
            .order_by(
                case(*[(ScanObservation.severity == severity, rank) for severity, rank in SEVERITY_RANK.items()], else_=5),
                ScanObservation.host,
                ScanObservation.port,
                ScanObservation.id,
            )
            .limit(per_type)
        )).scalars().all()
        results.extend({
            "type": "asset",
            "id": observation.fingerprint,
            "title": observation.title,
            "subtitle": f"{observation.host}{f':{observation.port}' if observation.port is not None else ''} · {latest_snapshot.label}",
            "snippet": _search_snippet(
                query,
                observation.host,
                observation.title,
                observation.tool,
                _observation_evidence_search_text(observation.evidence_ref),
            ),
            "tab": "assets",
            "host": _normalize_host(observation.host) or observation.host,
        } for observation in observation_rows)

    attack_path_rows = (await db.execute(
        select(AttackPath)
        .where(
            AttackPath.engagement_id == engagement_id,
            or_(
                AttackPath.name.ilike(pattern, escape="\\"),
                AttackPath.description.ilike(pattern, escape="\\"),
                AttackPath.narrative.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(AttackPath.created_at.desc(), AttackPath.id)
        .limit(per_type)
    )).scalars().all()
    results.extend({
        "type": "exploitation chain",
        "id": path.id,
        "title": path.name,
        "subtitle": f"{(path.risk_level or 'unrated').title()} risk",
        "snippet": _search_snippet(query, path.name, path.description, path.narrative),
        "tab": "attack_paths",
    } for path in attack_path_rows)

    total_matches = len(results)
    return {
        "query": query,
        "count": min(total_matches, limit),
        "limited": total_matches > limit or any(
            len(rows) == per_type
            for rows in (
                finding_rows,
                checklist_rows,
                evidence_rows,
                note_rows,
                note_attachment_rows,
                attack_path_rows,
            )
        ),
        "results": results[:limit],
    }


def _csv_safe(value, redact_sensitive: bool) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    if redact_sensitive:
        text = redact_sensitive_text(text)
    text = text.replace("\x00", "")
    formula_candidate = text.lstrip(" \t\r\n")
    if (
        formula_candidate.startswith(("=", "+", "-", "@"))
        or text.startswith(("\t", "\r"))
    ):
        text = "'" + text
    return text


@router.get("/findings.csv")
async def export_findings_csv(
    engagement_id: str,
    redact_sensitive: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export accepted findings as deterministic, spreadsheet-safe CSV."""
    engagement = await _require_engagement(db, engagement_id)
    findings = list((await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .order_by(
            case(*[(Finding.severity == severity, rank) for severity, rank in SEVERITY_RANK.items()], else_=5),
            Finding.cvss_score.desc(),
            Finding.created_at,
            Finding.id,
        )
    )).scalars().all())
    output = StringIO(newline="")
    fieldnames = [
        "id",
        "title",
        "severity",
        "cvss_score",
        "affected_hosts",
        "retest_status",
        "retest_due_date",
        "source",
        "description",
        "evidence",
        "remediation",
        "evidence_refs",
        "created_at",
        "updated_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for finding in findings:
        writer.writerow({
            field: _csv_safe(getattr(finding, field), redact_sensitive)
            for field in fieldnames
        })
    suffix = "-redacted" if redact_sensitive else ""
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", engagement.name).strip("-") or "engagement"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}-findings{suffix}.csv"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/assets")
async def asset_inventory(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build a current host and service inventory from immutable scan snapshots."""
    await _require_engagement(db, engagement_id)
    snapshots = list((await db.execute(
        select(ScanSnapshot)
        .where(ScanSnapshot.engagement_id == engagement_id)
        .order_by(ScanSnapshot.created_at.desc(), ScanSnapshot.id.desc())
    )).scalars().all())
    if not snapshots:
        return {
            "snapshot": None,
            "summary": {
                "assets": 0,
                "services": 0,
                "vulnerabilities": 0,
                "linked_findings": 0,
                "unlinked_findings": 0,
                "limited": False,
                "asset_limit": MAX_ASSET_INVENTORY_ITEMS,
                "observation_limit_per_type": MAX_ASSET_OBSERVATIONS_PER_TYPE,
                "finding_limit_per_asset": MAX_ASSET_FINDINGS_PER_HOST,
            },
            "assets": [],
        }

    current = snapshots[0]
    _, previous, current_items, previous_items, older_fingerprints = (
        await _comparison_material(db, engagement_id, current)
    )
    current_keys = set(current_items)
    previous_keys = set(previous_items)
    appeared = current_keys - previous_keys
    status_by_fingerprint = {
        fingerprint: (
            "regressed"
            if fingerprint in appeared and fingerprint in older_fingerprints
            else "new"
            if fingerprint in appeared
            else "persistent"
        )
        for fingerprint in current_keys
    }

    grouped: dict[str, list[ScanObservation]] = {}
    raw_hosts: dict[str, set[str]] = {}
    aliases_by_host: dict[str, set[str]] = {}
    operating_systems_by_host: dict[str, set[str]] = {}
    for observation in current_items.values():
        host = _normalize_host(observation.host) or "unknown"
        grouped.setdefault(host, []).append(observation)
        raw_hosts.setdefault(host, set()).add(observation.host)
        ref = observation.evidence_ref if isinstance(observation.evidence_ref, dict) else {}
        aliases_by_host.setdefault(host, set()).update(
            alias
            for value in (ref.get("hostnames") or [])
            if (alias := _normalize_host(value)) and alias != host
        )
        operating_system = str(ref.get("operating_system") or "").strip()
        if operating_system:
            operating_systems_by_host.setdefault(host, set()).add(operating_system)

    total_asset_count = len(grouped)
    total_services = 0
    total_vulnerabilities = 0
    for observations in grouped.values():
        for observation in observations:
            ref = observation.evidence_ref if isinstance(observation.evidence_ref, dict) else {}
            if any(ref.get(key) is not None for key in ("service", "protocol", "product", "version")):
                total_services += 1
            else:
                total_vulnerabilities += 1
    selected_hosts = sorted(grouped)[:MAX_ASSET_INVENTORY_ITEMS]
    selected_raw_hosts = {
        raw_host
        for host in selected_hosts
        for raw_host in raw_hosts[host]
    }
    history: dict[str, dict] = {
        host: {"snapshot_ids": set(), "first_seen": None, "last_seen": None}
        for host in selected_hosts
    }
    if selected_raw_hosts:
        history_rows = (await db.execute(
            select(ScanObservation.host, ScanSnapshot.id, ScanSnapshot.created_at)
            .join(ScanSnapshot, ScanSnapshot.id == ScanObservation.snapshot_id)
            .where(
                ScanSnapshot.engagement_id == engagement_id,
                ScanObservation.host.in_(selected_raw_hosts),
            )
        )).all()
        for raw_host, snapshot_id, created_at in history_rows:
            host = _normalize_host(raw_host) or "unknown"
            if host not in history:
                continue
            item = history[host]
            item["snapshot_ids"].add(snapshot_id)
            item["first_seen"] = min(item["first_seen"], created_at) if item["first_seen"] else created_at
            item["last_seen"] = max(item["last_seen"], created_at) if item["last_seen"] else created_at

    findings = list((await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .order_by(
            case(*[(Finding.severity == severity, rank) for severity, rank in SEVERITY_RANK.items()], else_=5),
            Finding.created_at,
            Finding.id,
        )
    )).scalars().all())
    finding_ids = [finding.id for finding in findings]
    attachment_counts = dict((await db.execute(
        select(EvidenceAttachment.finding_id, func.count(EvidenceAttachment.id))
        .where(EvidenceAttachment.finding_id.in_(finding_ids))
        .group_by(EvidenceAttachment.finding_id)
    )).all()) if finding_ids else {}
    findings_by_host: dict[str, list[Finding]] = {host: [] for host in selected_hosts}
    findings_by_observation = {
        ref.get("scan_observation_fingerprint"): finding.id
        for finding in findings
        for ref in (finding.evidence_refs or [])
        if isinstance(ref, dict) and ref.get("scan_observation_fingerprint")
    }
    identity_to_primary = {
        identity: host
        for host in grouped
        for identity in {host, *aliases_by_host.get(host, set())}
    }
    linked_finding_ids: set[str] = set()
    for finding in findings:
        for identity in _finding_hosts(finding):
            host = identity_to_primary.get(identity)
            if host:
                linked_finding_ids.add(finding.id)
                if host in findings_by_host and finding not in findings_by_host[host]:
                    findings_by_host[host].append(finding)

    status_rank = {"regressed": 0, "new": 1, "persistent": 2}
    assets = []
    for host in selected_hosts:
        observations = sorted(
            grouped[host],
            key=lambda item: (
                SEVERITY_RANK.get(str(item.severity).lower(), 5),
                item.port is None,
                item.port or 0,
                item.title.lower(),
                item.fingerprint,
            ),
        )
        services = []
        vulnerabilities = []
        for observation in observations:
            ref = observation.evidence_ref if isinstance(observation.evidence_ref, dict) else {}
            row = _observation_response(
                observation,
                status_by_fingerprint[observation.fingerprint],
            )
            row["finding_id"] = findings_by_observation.get(observation.fingerprint)
            if any(ref.get(key) is not None for key in ("service", "protocol", "product", "version")):
                services.append(row)
            else:
                vulnerabilities.append(row)
        linked = findings_by_host[host]
        states = [status_by_fingerprint[item.fingerprint] for item in observations]
        highest_severity = min(
            (str(item.severity).lower() for item in observations),
            key=lambda severity: SEVERITY_RANK.get(severity, 5),
            default="info",
        )
        assets.append({
            "host": host,
            "display_hosts": sorted(raw_hosts[host]),
            "aliases": sorted(aliases_by_host.get(host, set())),
            "operating_systems": sorted(operating_systems_by_host.get(host, set())),
            "status": min(states, key=lambda value: status_rank[value]),
            "highest_severity": highest_severity,
            "first_seen": history[host]["first_seen"],
            "last_seen": history[host]["last_seen"],
            "snapshot_count": len(history[host]["snapshot_ids"]),
            "service_count": len(services),
            "vulnerability_count": len(vulnerabilities),
            "finding_count": len(linked),
            "services": services[:MAX_ASSET_OBSERVATIONS_PER_TYPE],
            "vulnerabilities": vulnerabilities[:MAX_ASSET_OBSERVATIONS_PER_TYPE],
            "details_limited": (
                len(services) > MAX_ASSET_OBSERVATIONS_PER_TYPE
                or len(vulnerabilities) > MAX_ASSET_OBSERVATIONS_PER_TYPE
                or len(linked) > MAX_ASSET_FINDINGS_PER_HOST
            ),
            "findings": [
                {
                    "id": finding.id,
                    "title": finding.title,
                    "severity": _severity_value(finding.severity),
                    "retest_status": finding.retest_status,
                    "retest_due_date": finding.retest_due_date,
                    "evidence_attachment_count": attachment_counts.get(finding.id, 0),
                }
                for finding in linked[:MAX_ASSET_FINDINGS_PER_HOST]
            ],
        })

    return {
        "snapshot": _snapshot_response(current),
        "baseline": _snapshot_response(previous) if previous else None,
        "summary": {
            "assets": total_asset_count,
            "services": total_services,
            "vulnerabilities": total_vulnerabilities,
            "linked_findings": len(linked_finding_ids),
            "unlinked_findings": len(findings) - len(linked_finding_ids),
            "limited": total_asset_count > MAX_ASSET_INVENTORY_ITEMS,
            "asset_limit": MAX_ASSET_INVENTORY_ITEMS,
            "observation_limit_per_type": MAX_ASSET_OBSERVATIONS_PER_TYPE,
            "finding_limit_per_asset": MAX_ASSET_FINDINGS_PER_HOST,
        },
        "assets": assets,
    }


@router.post("/scan-snapshots", status_code=201)
async def create_snapshot(
    engagement_id: str,
    body: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    await _require_engagement(db, engagement_id)
    unique_ids = list(dict.fromkeys(body.scan_ids))
    result = await db.execute(
        select(ScanUpload).where(
            ScanUpload.engagement_id == engagement_id,
            ScanUpload.id.in_(unique_ids),
        )
    )
    scans = result.scalars().all()
    if len(scans) != len(unique_ids):
        raise HTTPException(status_code=404, detail="One or more scan files were not found")

    by_tool: dict[str, list[dict]] = {}
    total_bytes = 0
    for scan in scans:
        if scan.scan_type == "custom":
            raise HTTPException(status_code=422, detail=f"{scan.filename} has no structured parser and cannot be snapshotted")
        payload = _read_snapshot_payload(
            scan.file_path,
            scan.filename,
            MAX_SNAPSHOT_BYTES - total_bytes,
        )
        total_bytes += len(payload)
        records = parse_structured(payload.decode("utf-8", errors="replace"), scan.scan_type)
        if not records:
            raise HTTPException(status_code=422, detail=f"No structured observations could be parsed from {scan.filename}")
        for record in records:
            record["_scan_id"] = scan.id
            record["_scan_filename"] = scan.filename
            record["_scan_type"] = scan.scan_type
            for vulnerability in record.get("vulns", []):
                vulnerability["_scan_id"] = scan.id
                vulnerability["_scan_filename"] = scan.filename
                vulnerability["_scan_type"] = scan.scan_type
        by_tool.setdefault(scan.scan_type, []).extend(records)

    correlated = correlate(by_tool)
    normalized: dict[str, dict] = {}
    host_metadata = {
        _normalize_host(host.get("host")): {
            "hostnames": sorted({
                normalized_hostname
                for value in (host.get("hostnames") or [])
                if (normalized_hostname := _normalize_host(value))
            }),
            "operating_system": host.get("os"),
        }
        for host in correlated["hosts"].values()
    }
    for finding in correlated["findings"]:
        for host in finding.get("hosts") or ["unknown"]:
            metadata = host_metadata.get(_normalize_host(host), {})
            fingerprint = _fingerprint(cve=finding.get("cve"), title=finding.get("title"), host=host, port=finding.get("port"))
            normalized[fingerprint] = {
                "fingerprint": fingerprint,
                "tool": ", ".join(sorted(finding.get("sources") or by_tool.keys()))[:50],
                "title": str(finding.get("title") or "Untitled observation")[:500],
                "severity": str(finding.get("severity") or "info")[:20],
                "host": str(host)[:500],
                "port": finding.get("port"),
                "evidence_ref": {
                    "cve": finding.get("cve"),
                    "sources": finding.get("sources") or [],
                    "evidence_refs": finding.get("evidence_refs") or [],
                    "hostnames": metadata.get("hostnames") or [],
                    "operating_system": metadata.get("operating_system"),
                },
            }
    for host in correlated["hosts"].values():
        for port_record in host.get("ports") or []:
            title = f"Open {port_record.get('service') or 'network'} service"
            fingerprint = _fingerprint(
                cve=None,
                title=title,
                host=host.get("host") or "unknown",
                port=port_record.get("port"),
            )
            normalized.setdefault(fingerprint, {
                "fingerprint": fingerprint,
                "tool": ", ".join(sorted(host.get("sources") or by_tool.keys()))[:50],
                "title": title[:500],
                "severity": "info",
                "host": str(host.get("host") or "unknown")[:500],
                "port": port_record.get("port"),
                "evidence_ref": {
                    "protocol": port_record.get("protocol"),
                    "service": port_record.get("service"),
                    "product": port_record.get("product"),
                    "version": port_record.get("version"),
                    "evidence_refs": port_record.get("evidence_refs") or [],
                    "hostnames": host_metadata.get(_normalize_host(host.get("host")), {}).get("hostnames") or [],
                    "operating_system": host.get("os"),
                },
            })
    if not normalized:
        raise HTTPException(status_code=422, detail="The selected scans contained no comparable findings or open services")

    snapshot = ScanSnapshot(
        engagement_id=engagement_id,
        label=body.label,
        source_scan_ids=unique_ids,
        parser_version=SNAPSHOT_PARSER_VERSION,
        observation_count=len(normalized),
        created_by=current_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    await db.flush()
    for item in normalized.values():
        db.add(ScanObservation(snapshot_id=snapshot.id, **item))
    await db.flush()
    await db.refresh(snapshot)
    return await _comparison(db, engagement_id, snapshot)


@router.get("/scan-snapshots/{snapshot_id}/comparison")
async def compare_snapshot(
    engagement_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ScanSnapshot).where(
            ScanSnapshot.id == snapshot_id,
            ScanSnapshot.engagement_id == engagement_id,
        )
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Scan snapshot not found")
    return await _comparison(db, engagement_id, snapshot)


@router.post(
    "/scan-snapshots/{snapshot_id}/observations/{fingerprint}/finding",
    response_model=FindingResponse,
    status_code=201,
)
async def accept_scan_observation(
    engagement_id: str,
    snapshot_id: str,
    fingerprint: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Accept one immutable scanner fact as a finding without requiring AI."""
    await _require_engagement(db, engagement_id)
    result = await db.execute(
        select(ScanObservation, ScanSnapshot)
        .join(ScanSnapshot, ScanSnapshot.id == ScanObservation.snapshot_id)
        .where(
            ScanSnapshot.id == snapshot_id,
            ScanSnapshot.engagement_id == engagement_id,
            ScanObservation.fingerprint == fingerprint,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Scan observation not found")
    observation, scan_snapshot = row

    existing_findings = list((await db.execute(
        select(Finding).where(Finding.engagement_id == engagement_id)
    )).scalars().all())
    for existing in existing_findings:
        if any(
            isinstance(ref, dict)
            and ref.get("scan_observation_fingerprint") == fingerprint
            for ref in (existing.evidence_refs or [])
        ):
            raise HTTPException(
                status_code=409,
                detail="This scan observation is already linked to an accepted finding",
            )

    evidence = observation.evidence_ref if isinstance(observation.evidence_ref, dict) else {}
    cve = evidence.get("cve")
    location = observation.host
    if observation.port is not None:
        location = f"{location}:{observation.port}"
    evidence_lines = [
        f"Snapshot: {scan_snapshot.label}",
        f"Scanner: {observation.tool}",
        f"Location: {location}",
    ]
    if cve:
        evidence_lines.append(f"CVE: {cve}")
    evidence_reference = {
        "id": f"SNAP-{fingerprint[:12].upper()}",
        "snapshot_id": scan_snapshot.id,
        "snapshot_label": scan_snapshot.label,
        "scan_observation_fingerprint": fingerprint,
        "tool": observation.tool,
        "host": observation.host,
        "port": observation.port,
        "cve": cve,
        "excerpt": observation.title,
        "source_evidence": evidence.get("evidence_refs") or [],
    }
    finding = Finding(
        engagement_id=engagement_id,
        title=observation.title,
        description=(
            "Accepted from a versioned scan observation. Review the impact, "
            "reproduction detail, and remediation before reporting."
        ),
        severity=(
            str(observation.severity).lower()
            if str(observation.severity).lower() in SEVERITY_RANK
            else "info"
        ),
        affected_hosts=location,
        evidence="\n".join(evidence_lines),
        evidence_refs=[evidence_reference],
        source="scan_reviewed",
        ai_inference=False,
        created_by=current_user.id,
    )
    db.add(finding)
    await db.flush()
    await record_history(
        db,
        finding,
        action="scan_observation_accepted",
        created_by=current_user.id,
        changes={
            field: {"from": None, "to": value}
            for field, value in finding_snapshot(finding).items()
            if value is not None
        },
        source="scan_reviewed",
    )
    return FindingResponse.model_validate(finding)


@router.get("/findings.sarif")
async def export_sarif(
    engagement_id: str,
    redact_sensitive: Annotated[bool, Query()] = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    engagement = await _require_engagement(db, engagement_id)
    findings = list((await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .order_by(Finding.created_at, Finding.id)
    )).scalars().all())
    rules = []
    results = []
    level_map = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "none"}
    for finding in findings:
        rule_id = f"BW-{finding.id}"
        severity = _severity_value(finding.severity)
        title = redact_sensitive_text(finding.title) if redact_sensitive else finding.title
        remediation = finding.remediation or "No remediation recorded."
        description = finding.description or finding.title
        host = (finding.affected_hosts or "engagement").split(",", 1)[0].strip()
        if redact_sensitive:
            remediation = redact_sensitive_text(remediation)
            description = redact_sensitive_text(description)
            host = redact_sensitive_text(host)
        rules.append({
            "id": rule_id,
            "name": title[:255],
            "shortDescription": {"text": title},
            "help": {"text": remediation},
            "properties": {"severity": severity, "cvss": float(finding.cvss_score) if finding.cvss_score is not None else None},
        })
        results.append({
            "ruleId": rule_id,
            "level": level_map.get(severity, "warning"),
            "message": {"text": description},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": host}}}],
            "properties": {"breachwrightFindingId": finding.id, "retestStatus": finding.retest_status},
        })
    document = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "Breachwright", "informationUri": "https://github.com/Advent-Cybersecurity/Breachwright", "rules": rules}},
            "automationDetails": {"description": {"text": engagement.name}},
            "results": results,
        }],
    }
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", engagement.name).strip("-") or "engagement"
    if redact_sensitive:
        safe_name = f"{safe_name}-redacted"
    return JSONResponse(
        document,
        media_type="application/sarif+json",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-findings.sarif"'},
    )
