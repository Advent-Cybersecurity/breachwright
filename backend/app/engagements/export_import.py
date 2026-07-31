import json
import logging
import math
import re
import uuid
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.checklists.models import ChecklistItem
from app.engagements.models import (
    AttackPath,
    AppSetting,
    Engagement,
    EngagementStatus,
    Finding,
    FindingHistory,
    Report,
    ScanObservation,
    ScanSnapshot,
    ScanUpload,
)
from app.engagements.schemas import EngagementCreate, FindingCreate
from pydantic import ValidationError
from app.findings.history import record_history, snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements", tags=["export_import"])

MAX_IMPORT_SIZE = 25 * 1024 * 1024
MAX_IMPORT_FINDINGS = 5000
MAX_IMPORT_ATTACK_PATHS = 1000
MAX_IMPORT_CHECKLIST_ITEMS = 10000
MAX_IMPORT_SCAN_SNAPSHOTS = 1000
MAX_IMPORT_SCAN_OBSERVATIONS = 100000
MAX_IMPORT_FINDING_HISTORY_ITEMS = 50000
MAX_ATTACK_PATH_DESCRIPTION_SIZE = 200000
MAX_ATTACK_PATH_STEPS = 1000
MAX_ATTACK_PATH_STEPS_SIZE = 500000
MAX_ATTACK_PATH_NARRATIVE_SIZE = 500000
MAX_ATTACK_PATH_MITRE_TECHNIQUES = 1000
MAX_ATTACK_PATH_MITRE_SIZE = 500000
VALID_RETEST_STATUSES = {
    None,
    "",
    "open",
    "remediated",
    "retest_needed",
    "accepted_risk",
}
MAX_EVIDENCE_REFS = 100
MAX_EVIDENCE_REFS_SIZE = 500_000
SUPPORTED_IMPORT_VERSIONS = {"1.0", "1.1"}
VALID_CHECKLIST_STATUSES = {"pending", "in_progress", "done", "na"}
VALID_OBSERVATION_SEVERITIES = {"critical", "high", "medium", "low", "info"}
MAX_OBSERVATION_EVIDENCE_SIZE = 500_000
MAX_HISTORY_CHANGES_SIZE = 500_000
MAX_ENGAGEMENT_NARRATIVE_SIZE = 2 * 1024 * 1024


def _validate_evidence_refs(value: object, finding_index: int) -> list[dict] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) > MAX_EVIDENCE_REFS
        or any(not isinstance(item, dict) for item in value)
        or len(json.dumps(value).encode("utf-8")) > MAX_EVIDENCE_REFS_SIZE
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Finding {finding_index} has invalid evidence references",
        )
    return value


def _serialize(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def _parse_import_date(value: object, field_name: str) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}") from exc


@router.get("/{engagement_id}/export")
async def export_engagement(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get engagement
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Get findings
    result = await db.execute(
        select(Finding)
        .where(Finding.engagement_id == engagement_id)
        .order_by(Finding.created_at, Finding.id)
    )
    findings = result.scalars().all()
    history_by_finding: dict[str, list[FindingHistory]] = {
        item.id: [] for item in findings
    }
    if history_by_finding:
        result = await db.execute(
            select(FindingHistory)
            .where(FindingHistory.finding_id.in_(list(history_by_finding)))
            .order_by(
                FindingHistory.finding_id,
                FindingHistory.created_at,
                FindingHistory.id,
            )
        )
        for entry in result.scalars().all():
            history_by_finding[entry.finding_id].append(entry)

    # Get attack paths
    result = await db.execute(
        select(AttackPath)
        .where(AttackPath.engagement_id == engagement_id)
        .order_by(AttackPath.created_at, AttackPath.id)
    )
    attack_paths = result.scalars().all()

    result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.engagement_id == engagement_id)
        .order_by(ChecklistItem.methodology, ChecklistItem.order_index, ChecklistItem.id)
    )
    checklist_items = result.scalars().all()

    result = await db.execute(
        select(ScanSnapshot)
        .where(ScanSnapshot.engagement_id == engagement_id)
        .order_by(ScanSnapshot.created_at, ScanSnapshot.id)
    )
    scan_snapshots = result.scalars().all()
    observations_by_snapshot: dict[str, list[ScanObservation]] = {
        item.id: [] for item in scan_snapshots
    }
    if observations_by_snapshot:
        result = await db.execute(
            select(ScanObservation)
            .where(ScanObservation.snapshot_id.in_(list(observations_by_snapshot)))
            .order_by(ScanObservation.snapshot_id, ScanObservation.fingerprint)
        )
        for observation in result.scalars().all():
            observations_by_snapshot[observation.snapshot_id].append(observation)

    result = await db.execute(
        select(AppSetting).where(AppSetting.key == f"narrative_{engagement_id}")
    )
    narrative_setting = result.scalar_one_or_none()
    engagement_narrative = None
    if narrative_setting:
        try:
            parsed_narrative = json.loads(narrative_setting.value)
            if isinstance(parsed_narrative, dict):
                engagement_narrative = parsed_narrative
        except json.JSONDecodeError:
            logger.warning(
                "Skipping malformed saved narrative for engagement %s",
                engagement_id,
            )

    export_data = {
        "version": "1.1",
        "exported_by": current_user.display_name,
        "engagement": {
            "name": eng.name,
            "client_name": eng.client_name,
            "scope": eng.scope,
            "status": eng.status.value if hasattr(eng.status, 'value') else eng.status,
            "start_date": _serialize(eng.start_date) if eng.start_date else None,
            "end_date": _serialize(eng.end_date) if eng.end_date else None,
            "template_key": eng.template_key,
        },
        "findings": [
            {
                "portable_id": f.id,
                "title": f.title,
                "description": f.description,
                "severity": f.severity.value if hasattr(f.severity, 'value') else f.severity,
                "cvss_score": float(f.cvss_score) if f.cvss_score is not None else None,
                "affected_hosts": f.affected_hosts,
                "evidence": f.evidence,
                "remediation": f.remediation,
                "source": f.source,
                "evidence_refs": f.evidence_refs,
                "ai_confidence": float(f.ai_confidence)
                if f.ai_confidence is not None
                else None,
                "ai_inference": f.ai_inference,
                "retest_status": f.retest_status,
                "retest_due_date": _serialize(f.retest_due_date) if f.retest_due_date else None,
                "created_at": _serialize(f.created_at),
                "history": [
                    {
                        "action": entry.action,
                        "changes": entry.changes,
                        "source": entry.source,
                        "created_at": _serialize(entry.created_at),
                    }
                    for entry in history_by_finding[f.id]
                ],
            }
            for f in findings
        ],
        "attack_paths": [
            {
                "name": ap.name,
                "description": ap.description,
                "steps": ap.steps,
                "risk_level": ap.risk_level,
                "narrative": ap.narrative,
                "mitre_techniques": ap.mitre_techniques,
            }
            for ap in attack_paths
        ],
        "checklists": [
            {
                "methodology": item.methodology,
                "category": item.category,
                "item": item.item,
                "description": item.description,
                "tools": item.tools,
                "techniques": item.techniques,
                "reference_url": item.reference_url,
                "status": item.status,
                "notes": item.notes,
                "order_index": item.order_index,
            }
            for item in checklist_items
        ],
        "scan_snapshots": [
            {
                "label": snapshot.label,
                "parser_version": snapshot.parser_version,
                "created_at": _serialize(snapshot.created_at),
                "observations": [
                    {
                        "fingerprint": observation.fingerprint,
                        "tool": observation.tool,
                        "title": observation.title,
                        "severity": observation.severity,
                        "host": observation.host,
                        "port": observation.port,
                        "evidence_ref": observation.evidence_ref,
                    }
                    for observation in observations_by_snapshot[snapshot.id]
                ],
            }
            for snapshot in scan_snapshots
        ],
        "engagement_narrative": engagement_narrative,
    }

    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", eng.name).strip("._")
    filename = f"{safe_name or 'engagement'}_export.json"
    content = json.dumps(export_data, indent=2, default=_serialize)
    if len(content.encode("utf-8")) > MAX_IMPORT_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                "This engagement exceeds the 25 MB portable export limit. "
                "Use a verified full backup from Settings instead."
            ),
        )

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_engagement(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    content = await file.read(MAX_IMPORT_SIZE + 1)
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=413, detail="Import file too large (max 25MB)")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    if not isinstance(data, dict) or "engagement" not in data or "findings" not in data:
        raise HTTPException(status_code=400, detail="Invalid export format: missing engagement or findings")
    if data.get("version") not in SUPPORTED_IMPORT_VERSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                "Unsupported export version. Supported versions: "
                + ", ".join(sorted(SUPPORTED_IMPORT_VERSIONS))
            ),
        )

    eng_data = data["engagement"]
    finding_data = data["findings"]
    attack_path_data = data.get("attack_paths", [])
    checklist_data = data.get("checklists", [])
    snapshot_data = data.get("scan_snapshots", [])
    engagement_narrative = data.get("engagement_narrative")
    if not isinstance(eng_data, dict):
        raise HTTPException(status_code=400, detail="Invalid engagement data")
    if not isinstance(finding_data, list):
        raise HTTPException(status_code=400, detail="Findings must be a list")
    if not isinstance(attack_path_data, list):
        raise HTTPException(status_code=400, detail="Attack paths must be a list")
    if not isinstance(checklist_data, list):
        raise HTTPException(status_code=400, detail="Checklists must be a list")
    if not isinstance(snapshot_data, list):
        raise HTTPException(status_code=400, detail="Scan snapshots must be a list")
    if engagement_narrative is not None and (
        not isinstance(engagement_narrative, dict)
        or len(json.dumps(engagement_narrative).encode("utf-8"))
        > MAX_ENGAGEMENT_NARRATIVE_SIZE
    ):
        raise HTTPException(status_code=422, detail="Invalid engagement narrative")
    if len(finding_data) > MAX_IMPORT_FINDINGS:
        raise HTTPException(
            status_code=413,
            detail=f"Import exceeds {MAX_IMPORT_FINDINGS} findings",
        )
    if len(attack_path_data) > MAX_IMPORT_ATTACK_PATHS:
        raise HTTPException(
            status_code=413,
            detail=f"Import exceeds {MAX_IMPORT_ATTACK_PATHS} attack paths",
        )
    if len(checklist_data) > MAX_IMPORT_CHECKLIST_ITEMS:
        raise HTTPException(
            status_code=413,
            detail=f"Import exceeds {MAX_IMPORT_CHECKLIST_ITEMS} checklist items",
        )
    if len(snapshot_data) > MAX_IMPORT_SCAN_SNAPSHOTS:
        raise HTTPException(
            status_code=413,
            detail=f"Import exceeds {MAX_IMPORT_SCAN_SNAPSHOTS} scan snapshots",
        )

    start_date = _parse_import_date(eng_data.get("start_date"), "engagement start date")
    end_date = _parse_import_date(eng_data.get("end_date"), "engagement end date")
    try:
        engagement_status = EngagementStatus(eng_data.get("status", "active"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid engagement status") from exc

    try:
        validated_engagement = EngagementCreate(
            name=eng_data.get("name", "Imported Engagement"),
            client_name=eng_data.get("client_name", "Unknown"),
            scope=eng_data.get("scope"),
            start_date=start_date,
            end_date=end_date,
            template_key=eng_data.get("template_key"),
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid engagement: {exc.errors()[0]['msg']}",
        ) from exc

    # Create engagement
    engagement = Engagement(
        name=validated_engagement.name,
        client_name=validated_engagement.client_name,
        scope=validated_engagement.scope,
        status=engagement_status,
        start_date=validated_engagement.start_date,
        end_date=validated_engagement.end_date,
        template_key=validated_engagement.template_key,
        created_by=current_user.id,
    )
    db.add(engagement)
    await db.flush()

    # Create findings
    finding_count = 0
    imported_findings: list[tuple[Finding, list, int]] = []
    finding_id_map: dict[str, str] = {}
    input_history_count = 0
    for index, fd in enumerate(finding_data):
        if not isinstance(fd, dict):
            raise HTTPException(
                status_code=422,
                detail=f"Finding {index + 1} must be an object",
            )
        if fd.get("retest_status") not in VALID_RETEST_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Finding {index + 1} has an invalid retest status",
            )
        history_data = fd.get("history", [])
        if not isinstance(history_data, list):
            raise HTTPException(
                status_code=422,
                detail=f"Finding {index + 1} has invalid history",
            )
        input_history_count += len(history_data)
        if input_history_count > MAX_IMPORT_FINDING_HISTORY_ITEMS:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Import exceeds "
                    f"{MAX_IMPORT_FINDING_HISTORY_ITEMS} finding history items"
                ),
            )
        portable_id = fd.get("portable_id")
        if portable_id is not None and (
            not isinstance(portable_id, str)
            or not portable_id.strip()
            or len(portable_id) > 100
            or portable_id in finding_id_map
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Finding {index + 1} has an invalid portable ID",
            )
        finding_source = fd.get("source", "imported")
        if (
            not isinstance(finding_source, str)
            or not finding_source.strip()
            or len(finding_source) > 50
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Finding {index + 1} has an invalid source",
            )
        ai_confidence = fd.get("ai_confidence")
        if ai_confidence is not None and (
            isinstance(ai_confidence, bool)
            or not isinstance(ai_confidence, (int, float))
            or not math.isfinite(float(ai_confidence))
            or not 0 <= float(ai_confidence) <= 1
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Finding {index + 1} has invalid AI confidence",
            )
        ai_inference = fd.get("ai_inference", False)
        if not isinstance(ai_inference, bool):
            raise HTTPException(
                status_code=422,
                detail=f"Finding {index + 1} has invalid AI provenance",
            )
        created_at = None
        if fd.get("created_at") is not None:
            try:
                created_at = datetime.fromisoformat(fd["created_at"])
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Finding {index + 1} has an invalid creation time",
                ) from exc
        try:
            validated_finding = FindingCreate(
                title=fd.get("title", "Untitled"),
                description=fd.get("description"),
                severity=fd.get("severity", "info"),
                cvss_score=fd.get("cvss_score"),
                affected_hosts=fd.get("affected_hosts"),
                evidence=fd.get("evidence"),
                remediation=fd.get("remediation"),
                retest_status=fd.get("retest_status") or None,
                retest_due_date=fd.get("retest_due_date"),
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid finding {index + 1}: {exc.errors()[0]['msg']}",
            ) from exc
        finding_values = dict(
            id=str(uuid.uuid4()),
            engagement_id=engagement.id,
            title=validated_finding.title,
            description=validated_finding.description,
            severity=validated_finding.severity,
            cvss_score=validated_finding.cvss_score,
            affected_hosts=validated_finding.affected_hosts,
            evidence=validated_finding.evidence,
            remediation=validated_finding.remediation,
            source=finding_source.strip(),
            evidence_refs=_validate_evidence_refs(fd.get("evidence_refs"), index + 1),
            ai_confidence=float(ai_confidence) if ai_confidence is not None else None,
            ai_inference=ai_inference,
            retest_status=fd.get("retest_status"),
            retest_due_date=validated_finding.retest_due_date,
            created_by=current_user.id,
        )
        if created_at is not None:
            finding_values["created_at"] = created_at
        finding = Finding(**finding_values)
        db.add(finding)
        if portable_id is not None:
            finding_id_map[portable_id] = finding.id
        imported_findings.append((finding, history_data, index + 1))
        finding_count += 1

    await db.flush()
    finding_history_count = 0
    for finding, history_data, finding_number in imported_findings:
        if not history_data:
            created_history = await record_history(
                db,
                finding,
                action="imported",
                created_by=current_user.id,
                changes={
                    field: {"from": None, "to": value}
                    for field, value in snapshot(finding).items()
                    if value is not None
                },
                source="imported",
            )
            finding_history_count += int(created_history is not None)
            continue

        last_history_created_at: datetime | None = None
        for history_index, history_item in enumerate(history_data, 1):
            if not isinstance(history_item, dict):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Finding {finding_number} history item {history_index} "
                        "must be an object"
                    ),
                )
            action = history_item.get("action")
            source = history_item.get("source")
            changes = history_item.get("changes")
            if not isinstance(action, str) or not action.strip() or len(action) > 50:
                raise HTTPException(
                    status_code=422,
                    detail=f"Finding {finding_number} history item {history_index} has invalid action",
                )
            if not isinstance(source, str) or not source.strip() or len(source) > 50:
                raise HTTPException(
                    status_code=422,
                    detail=f"Finding {finding_number} history item {history_index} has invalid source",
                )
            if (
                not isinstance(changes, dict)
                or len(json.dumps(changes).encode("utf-8"))
                > MAX_HISTORY_CHANGES_SIZE
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"Finding {finding_number} history item {history_index} has invalid changes",
                )
            try:
                created_at = datetime.fromisoformat(history_item.get("created_at"))
                if (
                    last_history_created_at is not None
                    and created_at <= last_history_created_at
                ):
                    created_at = last_history_created_at + timedelta(microseconds=1)
            except (OverflowError, TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Finding {finding_number} history item {history_index} has invalid creation time",
                ) from exc
            last_history_created_at = created_at
            db.add(FindingHistory(
                finding_id=finding.id,
                engagement_id=engagement.id,
                action=action.strip(),
                changes=changes,
                source=source.strip(),
                created_by=current_user.id,
                created_at=created_at,
            ))
            finding_history_count += 1

    checklist_count = 0
    for index, item_data in enumerate(checklist_data):
        if not isinstance(item_data, dict):
            raise HTTPException(
                status_code=422,
                detail=f"Checklist item {index + 1} must be an object",
            )

        def bounded_text(field: str, limit: int, *, required: bool = False):
            value = item_data.get(field)
            if value is None and not required:
                return None
            if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
                raise HTTPException(
                    status_code=422,
                    detail=f"Checklist item {index + 1} has invalid {field}",
                )
            return value.strip() if required else value

        status = item_data.get("status", "pending")
        if status not in VALID_CHECKLIST_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Checklist item {index + 1} has invalid status",
            )
        order_index = item_data.get("order_index", 0)
        if isinstance(order_index, bool) or not isinstance(order_index, int) or not 0 <= order_index <= 1_000_000:
            raise HTTPException(
                status_code=422,
                detail=f"Checklist item {index + 1} has invalid order index",
            )
        db.add(ChecklistItem(
            engagement_id=engagement.id,
            methodology=bounded_text("methodology", 100, required=True),
            category=bounded_text("category", 200, required=True),
            item=bounded_text("item", 500, required=True),
            description=bounded_text("description", 200000),
            tools=bounded_text("tools", 500),
            techniques=bounded_text("techniques", 500),
            reference_url=bounded_text("reference_url", 500),
            status=status,
            notes=bounded_text("notes", 200000),
            order_index=order_index,
            updated_by=current_user.id if status != "pending" or item_data.get("notes") else None,
        ))
        checklist_count += 1

    snapshot_count = 0
    observation_count = 0
    last_snapshot_created_at: datetime | None = None
    for snapshot_index, snapshot_item in enumerate(snapshot_data):
        if not isinstance(snapshot_item, dict):
            raise HTTPException(
                status_code=422,
                detail=f"Scan snapshot {snapshot_index + 1} must be an object",
            )
        label = snapshot_item.get("label")
        parser_version = snapshot_item.get("parser_version")
        observations = snapshot_item.get("observations")
        if not isinstance(label, str) or not label.strip() or len(label) > 255:
            raise HTTPException(
                status_code=422,
                detail=f"Scan snapshot {snapshot_index + 1} has an invalid label",
            )
        if not isinstance(parser_version, str) or not parser_version.strip() or len(parser_version) > 50:
            raise HTTPException(
                status_code=422,
                detail=f"Scan snapshot {snapshot_index + 1} has an invalid parser version",
            )
        if not isinstance(observations, list) or not observations:
            raise HTTPException(
                status_code=422,
                detail=f"Scan snapshot {snapshot_index + 1} has no observations",
            )
        observation_count += len(observations)
        if observation_count > MAX_IMPORT_SCAN_OBSERVATIONS:
            raise HTTPException(
                status_code=413,
                detail=f"Import exceeds {MAX_IMPORT_SCAN_OBSERVATIONS} scan observations",
            )
        created_at_value = snapshot_item.get("created_at")
        try:
            created_at = datetime.fromisoformat(created_at_value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Scan snapshot {snapshot_index + 1} has an invalid creation time",
            ) from exc
        if last_snapshot_created_at is not None:
            try:
                if created_at <= last_snapshot_created_at:
                    created_at = last_snapshot_created_at + timedelta(microseconds=1)
            except (OverflowError, TypeError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Scan snapshot creation times must use a consistent timezone format",
                ) from exc
        last_snapshot_created_at = created_at
        imported_snapshot = ScanSnapshot(
            engagement_id=engagement.id,
            label=label.strip(),
            source_scan_ids=[],
            parser_version=parser_version.strip(),
            observation_count=len(observations),
            created_by=current_user.id,
            created_at=created_at,
        )
        db.add(imported_snapshot)
        await db.flush()
        fingerprints: set[str] = set()
        for observation_index, observation in enumerate(observations):
            item_number = observation_index + 1
            if not isinstance(observation, dict):
                raise HTTPException(
                    status_code=422,
                    detail=f"Scan snapshot {snapshot_index + 1} observation {item_number} must be an object",
                )
            fingerprint = observation.get("fingerprint")
            if (
                not isinstance(fingerprint, str)
                or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                or fingerprint in fingerprints
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"Scan snapshot {snapshot_index + 1} observation {item_number} has an invalid fingerprint",
                )
            fingerprints.add(fingerprint)

            def observation_text(field: str, limit: int):
                value = observation.get(field)
                if not isinstance(value, str) or not value.strip() or len(value) > limit:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Scan snapshot {snapshot_index + 1} observation {item_number} has invalid {field}",
                    )
                return value.strip()

            port = observation.get("port")
            if port is not None and (
                isinstance(port, bool)
                or not isinstance(port, int)
                or not 0 <= port <= 65535
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"Scan snapshot {snapshot_index + 1} observation {item_number} has an invalid port",
                )
            evidence_ref = observation.get("evidence_ref")
            if (
                not isinstance(evidence_ref, dict)
                or len(json.dumps(evidence_ref).encode("utf-8"))
                > MAX_OBSERVATION_EVIDENCE_SIZE
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"Scan snapshot {snapshot_index + 1} observation {item_number} has invalid evidence",
                )
            severity = observation_text("severity", 20).lower()
            if severity not in VALID_OBSERVATION_SEVERITIES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Scan snapshot {snapshot_index + 1} observation {item_number} has invalid severity",
                )
            db.add(ScanObservation(
                snapshot_id=imported_snapshot.id,
                fingerprint=fingerprint,
                tool=observation_text("tool", 50),
                title=observation_text("title", 500),
                severity=severity,
                host=observation_text("host", 500),
                port=port,
                evidence_ref=evidence_ref,
            ))
        snapshot_count += 1

    # Create attack paths
    ap_count = 0
    for index, apd in enumerate(attack_path_data):
        if not isinstance(apd, dict):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} must be an object",
            )
        name_value = apd.get("name", "Unnamed")
        if not isinstance(name_value, str):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has an invalid name",
            )
        name = name_value.strip()
        if not name or len(name) > 500:
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has an invalid name",
            )
        description = apd.get("description")
        if description is not None and (
            not isinstance(description, str)
            or len(description) > MAX_ATTACK_PATH_DESCRIPTION_SIZE
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has an invalid description",
            )
        steps = apd.get("steps")
        if steps is not None and (
            not isinstance(steps, list)
            or len(steps) > MAX_ATTACK_PATH_STEPS
            or len(json.dumps(steps).encode("utf-8")) > MAX_ATTACK_PATH_STEPS_SIZE
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has invalid steps",
            )
        if steps is not None:
            steps = json.loads(json.dumps(steps))
            for step in steps:
                if not isinstance(step, dict) or "finding_id" not in step:
                    continue
                old_finding_id = step["finding_id"]
                if old_finding_id is None:
                    continue
                if not isinstance(old_finding_id, str):
                    raise HTTPException(
                        status_code=422,
                        detail=f"Attack path {index + 1} has an invalid finding reference",
                    )
                if old_finding_id in finding_id_map:
                    step["finding_id"] = finding_id_map[old_finding_id]
                elif data["version"] == "1.1":
                    raise HTTPException(
                        status_code=422,
                        detail=f"Attack path {index + 1} references an unknown finding",
                    )
        risk_level = apd.get("risk_level")
        if risk_level is not None and (
            not isinstance(risk_level, str) or len(risk_level) > 50
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has an invalid risk level",
            )
        narrative = apd.get("narrative")
        if narrative is not None and (
            not isinstance(narrative, str)
            or len(narrative) > MAX_ATTACK_PATH_NARRATIVE_SIZE
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has an invalid narrative",
            )
        mitre_techniques = apd.get("mitre_techniques")
        if mitre_techniques is not None and (
            not isinstance(mitre_techniques, list)
            or len(mitre_techniques) > MAX_ATTACK_PATH_MITRE_TECHNIQUES
            or len(json.dumps(mitre_techniques).encode("utf-8"))
            > MAX_ATTACK_PATH_MITRE_SIZE
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Attack path {index + 1} has invalid MITRE techniques",
            )
        ap = AttackPath(
            engagement_id=engagement.id,
            name=name,
            description=description,
            steps=steps,
            risk_level=risk_level,
            narrative=narrative,
            mitre_techniques=mitre_techniques,
        )
        db.add(ap)
        ap_count += 1

    await db.flush()

    if engagement_narrative is not None:
        engagement_narrative = json.loads(json.dumps(engagement_narrative))
        citations = engagement_narrative.get("citations")
        if isinstance(citations, list):
            remapped_citations = []
            for citation in citations:
                if not isinstance(citation, str) or not citation.startswith("FINDING:"):
                    remapped_citations.append(citation)
                    continue
                old_finding_id = citation.split(":", 1)[1]
                remapped_citations.append(
                    f"FINDING:{finding_id_map.get(old_finding_id, old_finding_id)}"
                )
            engagement_narrative["citations"] = remapped_citations
        db.add(AppSetting(
            key=f"narrative_{engagement.id}",
            value=json.dumps(engagement_narrative),
        ))
        await db.flush()

    logger.info(
        "Imported engagement '%s' with %d findings, %d checklist items, %d scan snapshots, and %d attack paths",
        engagement.name, finding_count, checklist_count, snapshot_count, ap_count,
    )

    return {
        "id": engagement.id,
        "name": engagement.name,
        "findings_imported": finding_count,
        "finding_history_items_imported": finding_history_count,
        "checklist_items_imported": checklist_count,
        "scan_snapshots_imported": snapshot_count,
        "attack_paths_imported": ap_count,
    }
