"""Tool Output Correlation — API Endpoints.

Provides:
  1. Standalone correlation endpoint (view correlated results without AI)
  2. Enhanced analysis endpoint that correlates first, then sends to AI

The standalone endpoint is useful for pentesters who want to see the
cross-referenced host/service map before running AI analysis.
"""
import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.engagements.models import Engagement, ScanUpload
from app.correlation.structured_parsers import parse_structured
from app.correlation.engine import correlate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements/{engagement_id}", tags=["correlation"])

MAX_CORRELATION_SCANS = 50
MAX_CORRELATION_FILE_BYTES = 50 * 1024 * 1024
MAX_CORRELATION_TOTAL_BYTES = 250 * 1024 * 1024


def _read_scan_text(file_path: str, filename: str) -> tuple[str, int]:
    if os.path.islink(file_path) or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=409,
            detail=f"Stored scan is unavailable: {filename}",
        )
    with open(file_path, "rb") as handle:
        payload = handle.read(MAX_CORRELATION_FILE_BYTES + 1)
    if len(payload) > MAX_CORRELATION_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{filename} exceeds the 50 MB no-AI correlation file limit."
            ),
        )
    return payload.decode("utf-8", errors="replace"), len(payload)


@router.post("/correlate")
async def correlate_scans(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Correlate all uploaded scans without running AI analysis.

    Returns the unified host map, correlated findings with confidence
    scores, and dedup stats. Useful for reviewing what the tools found
    before spending AI tokens.
    """
    correlated = await _load_and_correlate(db, engagement_id)
    if "error" in correlated:
        status = 404 if "not found" in correlated["error"].lower() else 400
        raise HTTPException(status_code=status, detail=correlated["error"])

    # Don't send the full descriptions in the response (too verbose)
    # Instead, send a clean summary per finding
    findings_summary = []
    for f in correlated["findings"]:
        findings_summary.append({
            "title": f["title"],
            "severity": f["severity"],
            "cvss": f.get("cvss"),
            "cve": f.get("cve"),
            "hosts": f["hosts"],
            "port": f.get("port"),
            "sources": f["sources"],
            "confidence": f["confidence"],
            "description": _best_description(f),
            "solution": _best_solution(f),
        })

    # Clean host map for response
    hosts_summary = {}
    for key, h in correlated["hosts"].items():
        hosts_summary[key] = {
            "host": h["host"],
            "hostnames": h["hostnames"],
            "os": h["os"],
            "port_count": len(h["ports"]),
            "ports": [
                {
                    "port": p["port"],
                    "protocol": p["protocol"],
                    "service": p["service"],
                    "product": p.get("product", ""),
                    "version": p.get("version", ""),
                }
                for p in h["ports"]
            ],
            "sources": h["sources"],
        }

    return {
        "hosts": hosts_summary,
        "findings": findings_summary,
        "stats": correlated["stats"],
    }


def _best_description(finding: dict) -> str:
    """Pick the best description from available sources."""
    # Prefer Nessus > Burp > Nuclei > nmap_nse
    preference = ["nessus", "burp", "nuclei", "nmap_nse"]
    for src in preference:
        if src in finding.get("descriptions", {}):
            return finding["descriptions"][src]
    # Fall back to first available
    descs = finding.get("descriptions", {})
    return next(iter(descs.values()), "") if descs else ""


def _best_solution(finding: dict) -> str:
    """Pick the best remediation from available sources."""
    preference = ["nessus", "burp", "nuclei", "nmap_nse"]
    for src in preference:
        if src in finding.get("solutions", {}):
            return finding["solutions"][src]
    sols = finding.get("solutions", {})
    return next(iter(sols.values()), "") if sols else ""


async def _load_and_correlate(db: AsyncSession, engagement_id: str) -> dict:
    """Load scans from DB, parse structurally, and correlate."""
    # Verify engagement
    result = await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    if not result.scalar_one_or_none():
        return {"error": "Engagement not found"}

    # Load scans
    scan_result = await db.execute(
        select(ScanUpload)
        .where(ScanUpload.engagement_id == engagement_id)
        .order_by(ScanUpload.created_at, ScanUpload.id)
        .limit(MAX_CORRELATION_SCANS + 1)
    )
    scans = scan_result.scalars().all()
    if not scans:
        return {"error": "No scan files uploaded for this engagement"}
    if len(scans) > MAX_CORRELATION_SCANS:
        raise HTTPException(
            status_code=413,
            detail=(
                "No-AI correlation supports up to 50 scan files at a time. "
                "Create a structured snapshot from a smaller selection."
            ),
        )

    expected_total_bytes = 0
    for scan in scans:
        if os.path.islink(scan.file_path) or not os.path.isfile(scan.file_path):
            raise HTTPException(
                status_code=409,
                detail=f"Stored scan is unavailable: {scan.filename}",
            )
        size_bytes = os.path.getsize(scan.file_path)
        if size_bytes > MAX_CORRELATION_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"{scan.filename} exceeds the 50 MB no-AI correlation file limit."
                ),
            )
        expected_total_bytes += size_bytes
    if expected_total_bytes > MAX_CORRELATION_TOTAL_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The combined scan input exceeds the 250 MB no-AI correlation limit.",
        )

    # Parse each scan structurally
    by_tool = {}
    text_fallbacks = []

    actual_total_bytes = 0
    for scan in scans:
        try:
            raw, size_bytes = await asyncio.to_thread(
                _read_scan_text,
                scan.file_path,
                scan.filename,
            )
        except HTTPException:
            raise
        except OSError as exc:
            logger.warning(
                "Stored scan read failed for %s with %s",
                scan.id,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=409,
                detail=f"Stored scan could not be read: {scan.filename}",
            ) from exc
        actual_total_bytes += size_bytes
        if actual_total_bytes > MAX_CORRELATION_TOTAL_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "The combined scan input changed while reading and now "
                    "exceeds the 250 MB no-AI correlation limit."
                ),
            )

        records = parse_structured(raw, scan.scan_type)

        if records:
            tool_key = scan.scan_type
            by_tool.setdefault(tool_key, []).extend(records)
            logger.info(
                "Structured parse: %s (%s) → %d host records",
                scan.filename, scan.scan_type, len(records),
            )
        else:
            # Structured parser couldn't handle it — keep raw for text fallback
            text_fallbacks.append(f"--- {scan.scan_type.upper()}: {scan.filename} ---\n{raw[:10000]}")
            logger.info(
                "Structured parse failed for %s, using text fallback",
                scan.filename,
            )

    if not by_tool and not text_fallbacks:
        return {"error": "Could not parse any scan files"}

    if not by_tool:
        # No structured data — return minimal result with text hint
        return {
            "hosts": {},
            "findings": [],
            "stats": {
                "total_hosts": 0, "total_ports": 0, "total_raw_vulns": 0,
                "correlated_findings": 0, "tools_used": [],
                "multi_source_findings": 0, "dedup_ratio": 0,
            },
            "text_fallback": "\n\n".join(text_fallbacks),
        }

    # Correlate
    correlated = correlate(by_tool)

    # Attach text fallbacks for formats we couldn't structurally parse
    if text_fallbacks:
        correlated["text_fallback"] = "\n\n".join(text_fallbacks)

    return correlated
