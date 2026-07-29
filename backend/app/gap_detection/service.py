"""Methodology Gap Detection — Scope-Aware Coverage Analysis.

Cross-references an engagement's findings, checklist progress, scan data,
and scope definition against the selected methodology to identify:
  1. NOT TESTED — methodology items with no corresponding findings or checklist activity
  2. UNDERTESTED — items with minimal coverage (1 finding where you'd expect several)
  3. SCOPE MISMATCHES — items the methodology requires but that aren't relevant to scope
     (flagged as intentional exclusions, not gaps)

The AI is the final judge — it reads the scope and determines what's relevant.
This prevents false gaps like "you didn't test wireless" on a web app engagement.
"""
import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.engagements.models import Engagement, Finding, ScanUpload, AttackPath
from app.checklists.models import ChecklistItem
from app.checklists.methodologies import METHODOLOGIES
from app.ai.provider import get_provider
from app.ai.prompts.loader import get_prompt

logger = logging.getLogger(__name__)

GAP_ANALYSIS_PROMPT = """You are an expert penetration testing QA reviewer. Your job is to review an engagement's coverage against a testing methodology and identify gaps — areas that should have been tested based on the scope but weren't.

CRITICAL RULES:
1. SCOPE IS KING. Only flag gaps that are relevant to the defined scope. If the scope is "external web application", do NOT flag missing wireless, physical, or AD testing.
2. Infer the engagement type from the scope description, findings, and scan data. Use this to filter what methodology items are applicable.
3. Be practical, not pedantic. A pentester doesn't need to document every single checklist item if their findings demonstrate they covered the area.
4. If a finding exists that clearly covers a methodology area, that area is NOT a gap even if the checklist item is unchecked.

ENGAGEMENT TYPE INFERENCE:
Based on the scope and findings, classify this engagement as one or more of:
- external_network: External IP ranges, perimeter testing
- internal_network: Internal network, lateral movement, AD
- web_application: Web app testing, OWASP-style
- wireless: WiFi/wireless testing
- social_engineering: Phishing, pretexting
- physical: Physical access testing
- cloud: AWS/Azure/GCP assessment
- active_directory: AD-focused assessment

Only flag gaps for categories that match the inferred engagement type.

Respond in valid JSON:
{
  "engagement_type": ["internal_network", "active_directory"],
  "scope_summary": "Brief interpretation of what's in scope",
  "gaps": [
    {
      "category": "Methodology category name",
      "item": "Specific methodology item",
      "severity": "high|medium|low",
      "type": "not_tested|undertested",
      "reason": "Why this is a gap, referencing what's missing from findings/scans",
      "recommendation": "Specific action to close the gap",
      "methodology_ref": "Reference URL or section"
    }
  ],
  "out_of_scope_items": [
    {
      "category": "Category name",
      "item": "Item name",
      "reason": "Why this isn't applicable to the current scope"
    }
  ],
  "coverage_score": 85,
  "summary": "2-3 sentence overall assessment of coverage quality"
}

SEVERITY GUIDE for gaps:
- high: Critical methodology area with zero coverage (e.g., no privilege escalation testing on an internal pentest)
- medium: Area partially covered but with obvious holes (e.g., found SQLi but didn't test other injection types)
- low: Nice-to-have testing that was skipped (e.g., no SNMP enumeration when SNMP wasn't found in scans)

coverage_score: 0-100 percentage of applicable methodology items that are adequately covered."""


async def gather_engagement_context(
    db: AsyncSession,
    engagement_id: str,
) -> Optional[dict]:
    """Gather all context needed for gap analysis."""

    # Engagement
    eng_result = await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    engagement = eng_result.scalar_one_or_none()
    if not engagement:
        return None

    # Findings
    findings_result = await db.execute(
        select(Finding).where(Finding.engagement_id == engagement_id)
    )
    findings = findings_result.scalars().all()

    # Checklist progress
    checklists_result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.engagement_id == engagement_id)
        .order_by(ChecklistItem.methodology, ChecklistItem.order_index)
    )
    checklist_items = checklists_result.scalars().all()

    # Scan uploads (what tools were used)
    scans_result = await db.execute(
        select(ScanUpload).where(ScanUpload.engagement_id == engagement_id)
    )
    scans = scans_result.scalars().all()

    # Attack paths
    paths_result = await db.execute(
        select(AttackPath).where(AttackPath.engagement_id == engagement_id)
    )
    attack_paths = paths_result.scalars().all()

    return {
        "engagement": engagement,
        "findings": findings,
        "checklist_items": checklist_items,
        "scans": scans,
        "attack_paths": attack_paths,
    }


def build_context_prompt(context: dict, methodology_key: str) -> str:
    """Build the user message with all engagement context for the AI."""

    engagement = context["engagement"]
    findings = context["findings"]
    checklist_items = context["checklist_items"]
    scans = context["scans"]
    attack_paths = context["attack_paths"]

    methodology = METHODOLOGIES.get(methodology_key)
    if not methodology:
        return ""

    lines = []

    # Engagement info
    lines.append("=== ENGAGEMENT ===")
    lines.append(f"Name: {engagement.name}")
    lines.append(f"Client: {engagement.client_name}")
    lines.append(f"Scope: {engagement.scope or 'Not defined'}")
    lines.append(f"Status: {engagement.status.value if hasattr(engagement.status, 'value') else engagement.status}")
    if engagement.start_date:
        lines.append(f"Start: {engagement.start_date}")
    if engagement.end_date:
        lines.append(f"End: {engagement.end_date}")
    lines.append("")

    # Findings summary
    lines.append(f"=== FINDINGS ({len(findings)} total) ===")
    if findings:
        sev_counts = {}
        for f in findings:
            sev = f.severity.value if hasattr(f.severity, 'value') else f.severity
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        lines.append(f"Severity breakdown: {sev_counts}")
        lines.append("")

        for f in findings:
            sev = f.severity.value if hasattr(f.severity, 'value') else f.severity
            lines.append(f"- [{sev.upper()}] {f.title}")
            if f.affected_hosts:
                lines.append(f"  Hosts: {f.affected_hosts}")
            if f.description:
                lines.append(f"  Description: {f.description[:200]}")
            lines.append("")
    else:
        lines.append("No findings recorded yet.")
        lines.append("")

    # Scan data
    lines.append(f"=== SCANS ({len(scans)} uploads) ===")
    if scans:
        for s in scans:
            lines.append(f"- {s.scan_type}: {s.filename}")
    else:
        lines.append("No scans uploaded.")
    lines.append("")

    # Attack paths
    if attack_paths:
        lines.append(f"=== ATTACK PATHS ({len(attack_paths)}) ===")
        for ap in attack_paths:
            lines.append(f"- [{ap.risk_level or 'unknown'}] {ap.name}")
            if ap.description:
                lines.append(f"  {ap.description[:150]}")
        lines.append("")

    # Checklist progress
    lines.append("=== CHECKLIST PROGRESS ===")
    if checklist_items:
        # Group by methodology
        by_meth = {}
        for ci in checklist_items:
            by_meth.setdefault(ci.methodology, []).append(ci)

        for meth_key, items in by_meth.items():
            done = sum(1 for i in items if i.status == "done")
            na = sum(1 for i in items if i.status == "na")
            progress = sum(1 for i in items if i.status in ("done", "na"))
            total = len(items)
            lines.append(f"\n{meth_key}: {done} done, {na} N/A, {total - progress} remaining out of {total}")

            for ci in items:
                status_icon = {"done": "✓", "in_progress": "◐", "na": "⊘", "pending": "○"}
                icon = status_icon.get(ci.status, "?")
                lines.append(f"  {icon} [{ci.status}] {ci.category} > {ci.item}")
                if ci.notes:
                    lines.append(f"    Notes: {ci.notes[:100]}")
    else:
        lines.append("No checklists populated for this engagement.")
    lines.append("")

    # Methodology being reviewed against
    lines.append(f"=== METHODOLOGY: {methodology['name']} ===")
    lines.append(f"Description: {methodology['description']}")
    lines.append(f"Total items: {len(methodology['items'])}")
    lines.append("")

    # Group methodology items by category
    by_cat = {}
    for item in methodology["items"]:
        by_cat.setdefault(item["category"], []).append(item)

    for cat, items in by_cat.items():
        lines.append(f"\n--- {cat} ---")
        for item in items:
            lines.append(f"  • {item['item']}")
            if item.get("description"):
                lines.append(f"    {item['description'][:150]}")

    return "\n".join(lines)


async def analyze_gaps(
    db: AsyncSession,
    engagement_id: str,
    methodology_key: str = "ptes",
) -> dict:
    """Run AI-powered methodology gap detection.

    Returns structured gap analysis with scope-aware filtering.
    """

    # Validate methodology
    if methodology_key not in METHODOLOGIES:
        return {"error": f"Unknown methodology: {methodology_key}"}

    # Gather context
    context = await gather_engagement_context(db, engagement_id)
    if not context:
        return {"error": "Engagement not found"}

    # Build prompt
    user_message = build_context_prompt(context, methodology_key)

    # Check for custom prompt, fall back to default
    custom_prompt = await get_prompt(db, "prompt_gap_analysis")
    system_prompt = custom_prompt if custom_prompt else GAP_ANALYSIS_PROMPT

    # Call AI
    provider = get_provider()
    try:
        response_text = await provider.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=4096,
            temperature=0.2,
        )
    except Exception as e:
        logger.error("AI provider error during gap analysis: %s", e)
        return {"error": f"AI provider error: {str(e)}"}

    # Parse response
    import json
    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("Failed to parse gap analysis response as JSON")
        return {
            "error": "AI returned invalid JSON",
            "raw_response": response_text[:2000],
        }

    # Enrich with metadata
    methodology = METHODOLOGIES[methodology_key]
    result["methodology"] = methodology_key
    result["methodology_name"] = methodology["name"]
    result["engagement_id"] = engagement_id
    result["engagement_name"] = context["engagement"].name
    result["finding_count"] = len(context["findings"])
    result["scan_count"] = len(context["scans"])

    # Count gap severities
    gaps = result.get("gaps", [])
    result["gap_count"] = len(gaps)
    result["gap_severity_breakdown"] = {
        "high": sum(1 for g in gaps if g.get("severity") == "high"),
        "medium": sum(1 for g in gaps if g.get("severity") == "medium"),
        "low": sum(1 for g in gaps if g.get("severity") == "low"),
    }

    logger.info(
        "Gap analysis for %s against %s: score=%s, gaps=%d (H:%d M:%d L:%d)",
        engagement_id, methodology_key,
        result.get("coverage_score", "?"),
        len(gaps),
        result["gap_severity_breakdown"]["high"],
        result["gap_severity_breakdown"]["medium"],
        result["gap_severity_breakdown"]["low"],
    )

    return result
