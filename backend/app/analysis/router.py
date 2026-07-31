import json
import os
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.engagements.models import Engagement, Finding, ScanUpload
from app.engagements.schemas import FindingResponse
from app.ai.provider import get_provider
from app.ai.output_validation import validate_ai_findings
from app.ai.prompts.loader import get_prompt
from app.analysis.parsers import parse_scan_file
from app.correlation.structured_parsers import parse_structured
from app.correlation.engine import correlate, to_ai_prompt
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements/{engagement_id}", tags=["analysis"])

ALLOWED_SCAN_TYPES = {"nmap", "nessus", "burp", "custom"}
MAX_SCAN_SIZE = 50 * 1024 * 1024


def _safe_upload_name(filename: str | None, fallback: str) -> str:
    name = (filename or fallback).replace("\\", "/").rsplit("/", 1)[-1]
    return name if name not in {"", ".", ".."} else fallback


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
    extension = os.path.splitext(display_name)[1][:20]
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


@router.post("/analyze", response_model=list[FindingResponse])
async def analyze_scans(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    # Get engagement
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    # Get uploaded scans
    scan_result = await db.execute(
        select(ScanUpload).where(ScanUpload.engagement_id == engagement_id)
    )
    scans = scan_result.scalars().all()
    if not scans:
        raise HTTPException(status_code=400, detail="No scan files uploaded for this engagement")

    # Read and parse scan data — try structured correlation first, fall back to text
    by_tool = {}
    text_fallbacks = []
    for scan in scans:
        try:
            with open(scan.file_path, "r", errors="replace") as f:
                raw = f.read()
            # Try structured parsing
            records = parse_structured(raw, scan.scan_type)
            if records:
                by_tool.setdefault(scan.scan_type, []).extend(records)
            else:
                # Fall back to text parser
                parsed = parse_scan_file(raw, scan.scan_type)
                text_fallbacks.append(f"--- {scan.scan_type.upper()}: {scan.filename} ---\n{parsed}")
        except Exception as e:
            logger.warning("Could not read scan file %s: %s", scan.file_path, e)

    if not by_tool and not text_fallbacks:
        raise HTTPException(status_code=400, detail="Could not read any scan files")

    # Build AI prompt — correlated if possible, raw text otherwise
    if by_tool:
        correlated = correlate(by_tool)
        scan_text = to_ai_prompt(correlated)
        logger.info(
            "Correlation: %d tools, %d raw vulns → %d correlated findings (%.0f%% dedup)",
            len(correlated["stats"]["tools_used"]),
            correlated["stats"]["total_raw_vulns"],
            correlated["stats"]["correlated_findings"],
            correlated["stats"]["dedup_ratio"] * 100,
        )
        if text_fallbacks:
            scan_text += "\n\n=== ADDITIONAL SCAN DATA (unstructured) ===\n" + "\n".join(text_fallbacks)
    else:
        scan_text = "\n".join(text_fallbacks)

    # Call AI provider with custom prompt
    provider = get_provider()
    system_prompt = await get_prompt(db, "prompt_analysis")
    user_message = (
        f"Engagement: {engagement.name}\n"
        f"Client: {engagement.client_name}\n"
        f"Scope: {engagement.scope or 'Not specified'}\n\n"
        f"{scan_text}"
    )

    try:
        response_text = await provider.complete(
            system_prompt=system_prompt,
            user_message=user_message,
        )
    except Exception as e:
        logger.error("AI provider error: %s", e)
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}")

    # Parse findings from AI response — handle various AI output quirks
    findings_data = None
    cleaned = response_text.strip()
    # Try direct JSON parse first
    try:
        findings_data = json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    if findings_data is None:
        # Strip markdown fences: ```json ... ```
        import re
        json_match = re.search(r'```(?:json)?\s*\n?(\[.*?\])\s*```', cleaned, re.DOTALL)
        if json_match:
            try:
                findings_data = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

    if findings_data is None:
        # Look for a JSON array anywhere in the response
        bracket_start = cleaned.find('[')
        bracket_end = cleaned.rfind(']')
        if bracket_start != -1 and bracket_end > bracket_start:
            try:
                findings_data = json.loads(cleaned[bracket_start:bracket_end + 1])
            except json.JSONDecodeError:
                pass

    if findings_data is None:
        # AI returned no parseable findings — might be legitimate (no vulns found)
        logger.warning("Could not parse AI response as JSON. Response: %s", cleaned[:500])
        if any(phrase in cleaned.lower() for phrase in ["no significant", "no vulnerabilities", "no findings", "no issues"]):
            findings_data = []
        else:
            raise HTTPException(status_code=502, detail="AI returned invalid JSON response. Try re-running analysis.")

    if not isinstance(findings_data, list):
        findings_data = [findings_data] if isinstance(findings_data, dict) else []

    try:
        validated_findings = validate_ai_findings(findings_data)
    except ValueError as exc:
        logger.warning("Rejected invalid AI finding output: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Load existing findings for dedup
    from app.findings.dedup import find_duplicate, should_update_finding
    existing_result = await db.execute(
        select(Finding).where(Finding.engagement_id == engagement_id)
    )
    existing_findings = [
        {"id": f.id, "title": f.title, "severity": f.severity.value if hasattr(f.severity, 'value') else f.severity,
         "cvss_score": f.cvss_score, "affected_hosts": f.affected_hosts,
         "description": f.description, "remediation": f.remediation, "evidence": f.evidence}
        for f in existing_result.scalars().all()
    ]

    # Create or update findings
    created = []
    updated = 0
    for validated in validated_findings:
        fd = validated.model_dump(mode="json")
        new_title = fd["title"]
        new_hosts = fd.get("affected_hosts") or ""

        dup = find_duplicate(new_title, new_hosts, existing_findings)
        if dup:
            # Update existing finding
            updates = should_update_finding(dup, fd)
            if updates:
                dup_result = await db.execute(select(Finding).where(Finding.id == dup["id"]))
                dup_finding = dup_result.scalar_one_or_none()
                if dup_finding:
                    for k, v in updates.items():
                        setattr(dup_finding, k, v)
                    await db.flush()
                    updated += 1
            continue

        finding = Finding(
            engagement_id=engagement_id,
            title=validated.title,
            description=validated.description,
            severity=validated.severity,
            cvss_score=validated.cvss_score,
            affected_hosts=validated.affected_hosts,
            evidence=validated.evidence,
            remediation=validated.remediation,
            source="ai_generated",
            created_by=current_user.id,
        )
        db.add(finding)
        await db.flush()
        created.append(FindingResponse.model_validate(finding))

    logger.info("AI analysis: %d new, %d updated (deduped) for engagement %s", len(created), updated, engagement_id)

    # Keep cross-engagement intelligence current after every analysis.
    try:
        from app.knowledge.service import index_finding as kb_index
        all_findings = await db.execute(
            select(Finding).where(Finding.engagement_id == engagement_id)
        )
        for f in all_findings.scalars().all():
            await kb_index(db, f, engagement)
        logger.info("Knowledge base: indexed findings for engagement %s", engagement_id)
    except Exception as e:
        logger.warning("Knowledge base indexing failed: %s", e)
    return created
