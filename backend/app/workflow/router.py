"""Repeatable assessment, readiness, retest, and interoperability endpoints."""

import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.checklists.models import ChecklistItem
from app.db.session import get_db
from app.engagements.models import (
    AIFindingDraft,
    Engagement,
    EvidenceAttachment,
    Finding,
    ScanObservation,
    ScanSnapshot,
    ScanUpload,
)
from app.correlation.engine import correlate
from app.correlation.structured_parsers import parse_structured
from app.workflow.templates import ENGAGEMENT_TEMPLATES


router = APIRouter(prefix="/api/engagements/{engagement_id}", tags=["workflow"])
SNAPSHOT_PARSER_VERSION = "structured-v1"
MAX_SNAPSHOT_SCANS = 50
MAX_SNAPSHOT_BYTES = 250 * 1024 * 1024


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


async def _comparison(db: AsyncSession, engagement_id: str, current: ScanSnapshot) -> dict:
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
    for snapshot in prior[1:]:
        older_fingerprints.update((await _snapshot_observations(db, snapshot.id)).keys())

    current_keys = set(current_items)
    previous_keys = set(previous_items)
    persistent_keys = current_keys & previous_keys
    resolved_keys = previous_keys - current_keys
    appeared_keys = current_keys - previous_keys
    regressed_keys = appeared_keys & older_fingerprints
    new_keys = appeared_keys - regressed_keys

    def current_rows(keys, status):
        return [_observation_response(current_items[key], status) for key in sorted(keys)]

    return {
        "snapshot": _snapshot_response(current),
        "baseline": _snapshot_response(previous) if previous else None,
        "counts": {
            "new": len(new_keys),
            "persistent": len(persistent_keys),
            "resolved": len(resolved_keys),
            "regressed": len(regressed_keys),
        },
        "new": current_rows(new_keys, "new"),
        "persistent": current_rows(persistent_keys, "persistent"),
        "resolved": [_observation_response(previous_items[key], "resolved") for key in sorted(resolved_keys)],
        "regressed": current_rows(regressed_keys, "regressed"),
    }


@router.get("/workflow/templates")
async def list_templates(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_engagement(db, engagement_id)
    return [{"key": key, **value} for key, value in ENGAGEMENT_TEMPLATES.items()]


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
        .order_by(Finding.retest_due_date.is_(None), Finding.retest_due_date, Finding.severity)
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


@router.get("/report-readiness")
async def report_readiness(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    engagement = await _require_engagement(db, engagement_id)
    findings = list((await db.execute(select(Finding).where(Finding.engagement_id == engagement_id))).scalars().all())
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
    snapshot_count = int((await db.execute(
        select(func.count(ScanSnapshot.id)).where(ScanSnapshot.engagement_id == engagement_id)
    )).scalar_one())

    missing_evidence = [
        f for f in findings
        if _severity_value(f.severity) in {"critical", "high"}
        and not (f.evidence or f.evidence_refs or f.id in attachment_finding_ids)
    ]
    missing_remediation = [f for f in findings if _severity_value(f.severity) in {"critical", "high"} and not f.remediation]
    unresolved = [f for f in findings if f.retest_status in {"open", "retest_needed"}]
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
    if not snapshot_count:
        warnings.append({"code": "no_scan_snapshot", "message": "No versioned scan snapshot has been created."})
    score = max(0, 100 - 25 * len(blockers) - 5 * len(warnings))
    return {
        "ready": not blockers,
        "score": score,
        "blockers": blockers,
        "warnings": warnings,
        "summary": {
            "findings": len(findings),
            "pending_ai_drafts": pending_drafts,
            "unresolved_retests": len(unresolved),
            "checklist_incomplete": incomplete,
            "scan_snapshots": snapshot_count,
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
    for finding in correlated["findings"]:
        for host in finding.get("hosts") or ["unknown"]:
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


@router.get("/findings.sarif")
async def export_sarif(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    engagement = await _require_engagement(db, engagement_id)
    findings = list((await db.execute(select(Finding).where(Finding.engagement_id == engagement_id))).scalars().all())
    rules = []
    results = []
    level_map = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "none"}
    for index, finding in enumerate(findings, 1):
        rule_id = f"BW-{index:04d}"
        severity = _severity_value(finding.severity)
        rules.append({
            "id": rule_id,
            "name": finding.title[:255],
            "shortDescription": {"text": finding.title},
            "help": {"text": finding.remediation or "No remediation recorded."},
            "properties": {"severity": severity, "cvss": float(finding.cvss_score) if finding.cvss_score is not None else None},
        })
        host = (finding.affected_hosts or "engagement").split(",", 1)[0].strip()
        results.append({
            "ruleId": rule_id,
            "level": level_map.get(severity, "warning"),
            "message": {"text": finding.description or finding.title},
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
    return JSONResponse(
        document,
        media_type="application/sarif+json",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-findings.sarif"'},
    )
