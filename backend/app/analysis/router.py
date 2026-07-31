import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.engagements.models import AIFindingDraft, Engagement, Finding, ScanUpload
from app.engagements.schemas import FindingResponse
from app.ai.provider import get_provider
from app.ai.output_validation import validate_ai_findings
from app.ai.completion import complete_validated_json
from app.ai.prompts.loader import get_prompt
from app.ai.prompts.templates import ANALYSIS_GROUNDING_RULES, ANALYSIS_PROMPT_VERSION
from app.analysis.parsers import parse_scan_file
from app.analysis.context import (
    MAX_UNSTRUCTURED_SCAN_CHARS,
    build_untrusted_analysis_message,
    chunk_scan_text,
)
from app.correlation.structured_parsers import parse_structured
from app.correlation.engine import correlate, to_ai_prompt
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements/{engagement_id}", tags=["analysis"])

ALLOWED_SCAN_TYPES = {"nmap", "nessus", "burp", "custom"}
MAX_SCAN_SIZE = 50 * 1024 * 1024
RAW_EVIDENCE_SEGMENT_CHARS = 4000


class DraftEdit(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=200000)
    severity: Literal["critical", "high", "medium", "low", "info"] | None = None
    cvss_score: float | None = Field(default=None, ge=0, le=10)
    affected_hosts: str | None = Field(default=None, max_length=50000)
    evidence: str | None = Field(default=None, max_length=200000)
    remediation: str | None = Field(default=None, max_length=200000)

    model_config = {"str_strip_whitespace": True}


class BulkDraftReview(BaseModel):
    draft_ids: list[str] = Field(min_length=1, max_length=1000)
    action: Literal["accept", "reject"]


def _draft_response(draft: AIFindingDraft) -> dict:
    severity = draft.severity.value if hasattr(draft.severity, "value") else draft.severity
    return {
        "id": draft.id,
        "engagement_id": draft.engagement_id,
        "target_finding_id": draft.target_finding_id,
        "operation": draft.operation,
        "status": draft.status,
        "title": draft.title,
        "description": draft.description,
        "severity": severity,
        "cvss_score": float(draft.cvss_score) if draft.cvss_score is not None else None,
        "affected_hosts": draft.affected_hosts,
        "evidence": draft.evidence,
        "remediation": draft.remediation,
        "evidence_refs": draft.evidence_refs or [],
        "confidence": float(draft.confidence) if draft.confidence is not None else None,
        "provider": draft.provider,
        "prompt_version": draft.prompt_version,
        "created_at": draft.created_at,
        "reviewed_at": draft.reviewed_at,
    }


def _finding_snapshot(finding: Finding | None) -> dict | None:
    if finding is None:
        return None
    severity = finding.severity.value if hasattr(finding.severity, "value") else finding.severity
    return {
        "id": finding.id,
        "title": finding.title,
        "description": finding.description,
        "severity": severity,
        "cvss_score": float(finding.cvss_score) if finding.cvss_score is not None else None,
        "affected_hosts": finding.affected_hosts,
        "evidence": finding.evidence,
        "remediation": finding.remediation,
    }


def _raw_evidence(scan: ScanUpload, parsed: str, scan_index: int) -> tuple[str, list[dict]]:
    """Give bounded unstructured segments stable IDs and exact excerpts."""
    bounded = parsed[:MAX_UNSTRUCTURED_SCAN_CHARS]
    refs: list[dict] = []
    sections: list[str] = []
    for index in range(0, len(bounded), RAW_EVIDENCE_SEGMENT_CHARS):
        excerpt = bounded[index:index + RAW_EVIDENCE_SEGMENT_CHARS]
        evidence_id = f"RAW-{scan_index:04d}-E{len(refs) + 1:03d}"
        refs.append(
            {
                "id": evidence_id,
                "scan_id": scan.id,
                "filename": scan.filename,
                "scan_type": scan.scan_type,
                "tool": scan.scan_type,
                "host": None,
                "port": None,
                "cve": None,
                "plugin_id": None,
                "excerpt": excerpt,
                "correlation_confidence": 0.4,
            }
        )
        sections.append(
            f"--- Evidence ID {evidence_id}: {scan.scan_type.upper()} "
            f"file {scan.filename} ---\n{excerpt}"
        )
    if len(parsed) > len(bounded):
        sections.append(
            f"[Input truncated after {MAX_UNSTRUCTURED_SCAN_CHARS} characters for this scan.]"
        )
    return "\n".join(sections), refs


def _safe_upload_name(filename: str | None, fallback: str) -> str:
    name = (filename or fallback).replace("\\", "/").rsplit("/", 1)[-1]
    return name if name not in {"", ".", ".."} else fallback


def _safe_upload_extension(filename: str) -> str:
    """Return a portable suffix that cannot become an NTFS data stream."""
    extension = os.path.splitext(filename)[1].lower()
    suffix = extension[1:]
    if (
        extension.startswith(".")
        and len(extension) <= 20
        and suffix
        and all(character.isalnum() or character in {"-", "_"} for character in suffix)
    ):
        return extension
    return ".dat"


@router.get("/scans")
async def list_scans(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ScanUpload).where(ScanUpload.engagement_id == engagement_id)
    )
    scans = result.scalars().all()
    return [{"id": s.id, "filename": s.filename, "scan_type": s.scan_type} for s in scans]


@router.delete("/scans/{scan_id}", status_code=204)
async def delete_scan(
    engagement_id: str,
    scan_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(
        select(ScanUpload).where(ScanUpload.id == scan_id, ScanUpload.engagement_id == engagement_id)
    )
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Delete the file from disk
    if scan.file_path and os.path.exists(scan.file_path):
        try:
            os.remove(scan.file_path)
        except Exception as e:
            logger.warning("Could not delete scan file %s: %s", scan.file_path, e)

    await db.delete(scan)


@router.post("/upload-scan")
async def upload_scan(
    engagement_id: str,
    file: UploadFile = File(...),
    scan_type: str = "nmap",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    # Verify engagement exists
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
    if scan_type not in ALLOWED_SCAN_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported scan type")

    # Save file
    upload_dir = os.path.join(settings.data_dir, "uploads", engagement_id)
    os.makedirs(upload_dir, exist_ok=True)
    display_name = _safe_upload_name(file.filename, "scan.txt")
    extension = _safe_upload_extension(display_name)
    file_path = os.path.join(upload_dir, f"{uuid.uuid4().hex}{extension}")
    content = await file.read(MAX_SCAN_SIZE + 1)
    if len(content) > MAX_SCAN_SIZE:
        raise HTTPException(status_code=413, detail="Scan file too large (max 50MB)")
    with open(file_path, "wb") as f:
        f.write(content)

    scan = ScanUpload(
        engagement_id=engagement_id,
        filename=display_name,
        file_path=file_path,
        scan_type=scan_type,
        uploaded_by=current_user.id,
    )
    db.add(scan)
    await db.flush()

    return {"id": scan.id, "filename": scan.filename, "scan_type": scan.scan_type}


@router.post("/analyze")
async def analyze_scans(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Analyze scans into evidence-grounded proposals, never accepted findings."""
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    scan_result = await db.execute(
        select(ScanUpload).where(ScanUpload.engagement_id == engagement_id)
    )
    scans = scan_result.scalars().all()
    if not scans:
        raise HTTPException(
            status_code=400,
            detail="No scan files uploaded for this engagement",
        )

    by_tool: dict[str, list[dict]] = {}
    text_fallbacks: list[str] = []
    evidence_catalog: dict[str, dict] = {}
    for scan_index, scan in enumerate(scans, 1):
        try:
            with open(scan.file_path, "r", errors="replace") as source:
                raw = source.read()
            records = parse_structured(raw, scan.scan_type)
            if records:
                for record in records:
                    record["_scan_id"] = scan.id
                    record["_scan_filename"] = scan.filename
                    record["_scan_type"] = scan.scan_type
                    for vulnerability in record.get("vulns", []):
                        vulnerability["_scan_id"] = scan.id
                        vulnerability["_scan_filename"] = scan.filename
                        vulnerability["_scan_type"] = scan.scan_type
                by_tool.setdefault(scan.scan_type, []).extend(records)
            else:
                parsed = parse_scan_file(raw, scan.scan_type)
                raw_text, raw_refs = _raw_evidence(scan, parsed, scan_index)
                text_fallbacks.append(raw_text)
                evidence_catalog.update({ref["id"]: ref for ref in raw_refs})
        except Exception as exc:
            logger.warning("Could not read scan file %s: %s", scan.file_path, exc)

    if not by_tool and not text_fallbacks:
        raise HTTPException(status_code=400, detail="Could not read any scan files")

    if by_tool:
        correlated = correlate(by_tool)
        scan_text = to_ai_prompt(correlated)
        for host in correlated["hosts"].values():
            for port in host["ports"]:
                for ref in port.get("evidence_refs", []):
                    ref["correlation_confidence"] = 0.5
                    evidence_catalog[ref["id"]] = ref
        for correlated_finding in correlated["findings"]:
            for ref in correlated_finding["evidence_refs"]:
                ref["correlation_confidence"] = correlated_finding["confidence"]
                evidence_catalog[ref["id"]] = ref
        logger.info(
            "Correlation: %d tools, %d raw vulnerabilities to %d findings",
            len(correlated["stats"]["tools_used"]),
            correlated["stats"]["total_raw_vulns"],
            correlated["stats"]["correlated_findings"],
        )
        if text_fallbacks:
            scan_text += "\n\n=== ADDITIONAL UNSTRUCTURED EVIDENCE ===\n" + "\n".join(
                text_fallbacks
            )
    else:
        scan_text = "\n".join(text_fallbacks)

    chunks, truncated = chunk_scan_text(scan_text)
    provider = get_provider()
    custom_prompt = await get_prompt(db, "prompt_analysis")
    system_prompt = custom_prompt + ANALYSIS_GROUNDING_RULES
    validated_findings = []
    total_latency_ms = 0
    repaired_chunks = 0
    try:
        for chunk_index, chunk in enumerate(chunks, 1):
            candidates, metadata = await complete_validated_json(
                provider,
                system_prompt=system_prompt,
                user_message=build_untrusted_analysis_message(
                    engagement_name=engagement.name,
                    client_name=engagement.client_name,
                    scope=engagement.scope,
                    chunk=chunk,
                    chunk_index=chunk_index,
                    chunk_count=len(chunks),
                ),
                validator=validate_ai_findings,
            )
            validated_findings.extend(candidates)
            total_latency_ms += metadata.latency_ms
            repaired_chunks += int(metadata.repaired)
    except Exception as exc:
        logger.error("AI provider or validation error: %s", exc)
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}") from exc

    existing_result = await db.execute(
        select(Finding).where(Finding.engagement_id == engagement_id)
    )
    existing_findings = [
        {
            "id": finding.id,
            "title": finding.title,
            "severity": finding.severity.value
            if hasattr(finding.severity, "value")
            else finding.severity,
            "cvss_score": finding.cvss_score,
            "affected_hosts": finding.affected_hosts,
            "description": finding.description,
            "remediation": finding.remediation,
            "evidence": finding.evidence,
        }
        for finding in existing_result.scalars().all()
    ]

    from app.findings.dedup import find_duplicate

    grounded: list[tuple[object, list[dict], float]] = []
    unsupported_discarded = 0
    for validated in validated_findings:
        requested_refs = validated.evidence_refs
        if not requested_refs or any(
            ref_id not in evidence_catalog for ref_id in requested_refs
        ):
            unsupported_discarded += 1
            continue
        resolved_refs = [evidence_catalog[ref_id] for ref_id in requested_refs]
        cited_hosts = sorted(
            {str(ref["host"]) for ref in resolved_refs if ref.get("host")}
        )
        if cited_hosts:
            validated.affected_hosts = ", ".join(cited_hosts)
        evidence_confidence = min(
            float(ref.get("correlation_confidence", 0.4)) for ref in resolved_refs
        )
        confidence = min(
            evidence_confidence,
            float(validated.confidence)
            if validated.confidence is not None
            else evidence_confidence,
        )
        grounded.append((validated, resolved_refs, confidence))

    now = datetime.now(timezone.utc)
    await db.execute(
        update(AIFindingDraft)
        .where(
            AIFindingDraft.engagement_id == engagement_id,
            AIFindingDraft.status == "pending",
        )
        .values(status="superseded", reviewed_at=now)
    )

    drafts: list[AIFindingDraft] = []
    candidate_dedup = list(existing_findings)
    seen_target_ids: set[str] = set()
    for validated, resolved_refs, confidence in grounded:
        duplicate = find_duplicate(
            validated.title,
            validated.affected_hosts or "",
            candidate_dedup,
        )
        if duplicate and not duplicate.get("id"):
            continue
        target_id = duplicate.get("id") if duplicate and duplicate.get("id") else None
        if target_id and target_id in seen_target_ids:
            continue
        if target_id:
            seen_target_ids.add(target_id)
        draft = AIFindingDraft(
            engagement_id=engagement_id,
            target_finding_id=target_id,
            operation="update" if target_id else "create",
            status="pending",
            title=validated.title,
            description=validated.description,
            severity=validated.severity,
            cvss_score=validated.cvss_score,
            affected_hosts=validated.affected_hosts,
            evidence=validated.evidence,
            remediation=validated.remediation,
            evidence_refs=resolved_refs,
            confidence=confidence,
            provider=provider.name(),
            prompt_version=ANALYSIS_PROMPT_VERSION,
            created_by=current_user.id,
        )
        db.add(draft)
        await db.flush()
        drafts.append(draft)
        if not target_id:
            candidate_dedup.append(
                {
                    "id": None,
                    "title": validated.title,
                    "affected_hosts": validated.affected_hosts,
                }
            )

    logger.info(
        "AI analysis created %d drafts and discarded %d ungrounded candidates",
        len(drafts),
        unsupported_discarded,
    )
    return {
        "drafts": [_draft_response(draft) for draft in drafts],
        "summary": {
            "pending": len(drafts),
            "create_proposals": sum(d.operation == "create" for d in drafts),
            "update_proposals": sum(d.operation == "update" for d in drafts),
            "unsupported_discarded": unsupported_discarded,
            "chunks_analyzed": len(chunks),
            "input_truncated": truncated,
            "repair_attempts": repaired_chunks,
            "latency_ms": total_latency_ms,
            "provider": provider.name(),
            "prompt_version": ANALYSIS_PROMPT_VERSION,
        },
    }


@router.get("/ai-drafts")
async def list_ai_drafts(
    engagement_id: str,
    status: Literal["pending", "accepted", "rejected", "superseded", "all"] = Query(
        default="pending"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    engagement = await db.execute(
        select(Engagement.id).where(Engagement.id == engagement_id)
    )
    if not engagement.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
    query = select(AIFindingDraft).where(AIFindingDraft.engagement_id == engagement_id)
    if status != "all":
        query = query.where(AIFindingDraft.status == status)
    result = await db.execute(query.order_by(AIFindingDraft.created_at.desc()))
    drafts = result.scalars().all()
    target_ids = {draft.target_finding_id for draft in drafts if draft.target_finding_id}
    targets: dict[str, Finding] = {}
    if target_ids:
        target_result = await db.execute(
            select(Finding).where(
                Finding.engagement_id == engagement_id,
                Finding.id.in_(target_ids),
            )
        )
        targets = {finding.id: finding for finding in target_result.scalars().all()}
    responses = []
    for draft in drafts:
        response = _draft_response(draft)
        response["target_finding"] = _finding_snapshot(targets.get(draft.target_finding_id))
        responses.append(response)
    return responses


async def _get_pending_draft(
    db: AsyncSession,
    engagement_id: str,
    draft_id: str,
) -> AIFindingDraft:
    result = await db.execute(
        select(AIFindingDraft).where(
            AIFindingDraft.id == draft_id,
            AIFindingDraft.engagement_id == engagement_id,
        )
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="AI draft not found")
    if draft.status != "pending":
        raise HTTPException(status_code=409, detail="AI draft was already reviewed")
    return draft


async def _accept_draft(
    db: AsyncSession,
    engagement_id: str,
    draft: AIFindingDraft,
    current_user: User,
    edits: DraftEdit | None = None,
) -> Finding:
    values = {
        "title": draft.title,
        "description": draft.description,
        "severity": draft.severity,
        "cvss_score": draft.cvss_score,
        "affected_hosts": draft.affected_hosts,
        "evidence": draft.evidence,
        "remediation": draft.remediation,
    }
    if edits is not None:
        values.update(edits.model_dump(exclude_unset=True))

    finding = None
    if draft.target_finding_id:
        finding_result = await db.execute(
            select(Finding).where(
                Finding.id == draft.target_finding_id,
                Finding.engagement_id == engagement_id,
            )
        )
        finding = finding_result.scalar_one_or_none()
    if finding is None:
        finding = Finding(
            engagement_id=engagement_id,
            created_by=current_user.id,
            source="ai_reviewed",
            **values,
        )
        db.add(finding)
    else:
        for key, value in values.items():
            setattr(finding, key, value)
        finding.source = "ai_reviewed"

    finding.evidence_refs = draft.evidence_refs
    finding.ai_confidence = draft.confidence
    finding.ai_inference = True
    await db.flush()

    draft.status = "accepted"
    draft.target_finding_id = finding.id
    draft.reviewed_at = datetime.now(timezone.utc)
    await db.flush()

    try:
        from app.knowledge.service import index_finding

        engagement_result = await db.execute(
            select(Engagement).where(Engagement.id == engagement_id)
        )
        engagement = engagement_result.scalar_one()
        await index_finding(db, finding, engagement)
    except Exception as exc:
        logger.warning("Knowledge base indexing failed after AI draft review: %s", exc)
    return finding


@router.post("/ai-drafts/{draft_id}/accept", response_model=FindingResponse)
async def accept_ai_draft(
    engagement_id: str,
    draft_id: str,
    edits: DraftEdit | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    draft = await _get_pending_draft(db, engagement_id, draft_id)
    finding = await _accept_draft(db, engagement_id, draft, current_user, edits)
    return FindingResponse.model_validate(finding)


@router.post("/ai-drafts/{draft_id}/reject")
async def reject_ai_draft(
    engagement_id: str,
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    draft = await _get_pending_draft(db, engagement_id, draft_id)
    draft.status = "rejected"
    draft.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    return _draft_response(draft)


@router.post("/ai-drafts/bulk")
async def bulk_review_ai_drafts(
    engagement_id: str,
    body: BulkDraftReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(
        select(AIFindingDraft)
        .where(
            AIFindingDraft.engagement_id == engagement_id,
            AIFindingDraft.id.in_(body.draft_ids),
            AIFindingDraft.status == "pending",
        )
        .order_by(AIFindingDraft.created_at)
    )
    drafts = result.scalars().all()
    if len(drafts) != len(set(body.draft_ids)):
        raise HTTPException(
            status_code=409,
            detail="One or more AI drafts are missing or were already reviewed",
        )

    accepted: list[FindingResponse] = []
    if body.action == "accept":
        for draft in drafts:
            finding = await _accept_draft(
                db,
                engagement_id,
                draft,
                current_user,
            )
            accepted.append(FindingResponse.model_validate(finding))
    else:
        reviewed_at = datetime.now(timezone.utc)
        for draft in drafts:
            draft.status = "rejected"
            draft.reviewed_at = reviewed_at
        await db.flush()

    return {
        "action": body.action,
        "reviewed": len(drafts),
        "findings": accepted,
    }
