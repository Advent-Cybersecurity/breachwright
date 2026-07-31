import json
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.ad.models import ADImport, ADObject, ADRelationship, ADAttackPath
from app.engagements.models import Engagement
from app.ad.parser import parse_sharphound_zip, build_ad_summary
from app.ad.prompts import AD_ANALYSIS_PROMPT
from app.ai.provider import get_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements/{engagement_id}/ad", tags=["active_directory"])


@router.get("/imports")
async def list_ad_imports(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ADImport)
        .where(ADImport.engagement_id == engagement_id)
        .order_by(ADImport.created_at.desc())
    )
    imports = result.scalars().all()
    return [
        {
            "id": i.id,
            "filename": i.filename,
            "domain": i.domain,
            "object_count": i.object_count,
            "relationship_count": i.relationship_count,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in imports
    ]


@router.post("/import")
async def import_sharphound(
    engagement_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    engagement_result = await db.execute(
        select(Engagement.id).where(Engagement.id == engagement_id)
    )
    if not engagement_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Engagement not found")
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Expected a ZIP file (SharpHound/BloodHound output)")

    content = await file.read()
    if len(content) > 100 * 1024 * 1024:  # 100MB limit
        raise HTTPException(status_code=413, detail="File too large (max 100MB)")

    # Parse
    try:
        result = parse_sharphound_zip(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("SharpHound parse error: %s", e)
        raise HTTPException(status_code=400, detail=f"Failed to parse SharpHound data: {e}")

    if not result.objects:
        raise HTTPException(status_code=400, detail="No AD objects found in the ZIP file")

    # Create import record
    ad_import = ADImport(
        engagement_id=engagement_id,
        filename=file.filename,
        domain=result.domain,
        object_count=len(result.objects),
        relationship_count=len(result.relationships),
        imported_by=current_user.id,
    )
    db.add(ad_import)
    await db.flush()

    # Store objects
    for obj_data in result.objects:
        obj = ADObject(
            import_id=ad_import.id,
            object_id=obj_data["object_id"],
            name=obj_data["name"],
            object_type=obj_data["object_type"],
            domain=obj_data.get("domain"),
            enabled=obj_data.get("enabled", True),
            properties=obj_data.get("properties"),
        )
        db.add(obj)

    # Store relationships
    for rel_data in result.relationships:
        rel = ADRelationship(
            import_id=ad_import.id,
            source_id=rel_data["source_id"],
            target_id=rel_data["target_id"],
            relationship_type=rel_data["relationship_type"],
            is_inherited=rel_data.get("is_inherited", False),
        )
        db.add(rel)

    await db.flush()

    logger.info(
        "Imported SharpHound data: %d objects, %d relationships, domain: %s",
        len(result.objects), len(result.relationships), result.domain,
    )

    return {
        "id": ad_import.id,
        "domain": result.domain,
        "stats": result.stats,
        "object_count": len(result.objects),
        "relationship_count": len(result.relationships),
    }


@router.delete("/imports/{import_id}", status_code=204)
async def delete_ad_import(
    engagement_id: str,
    import_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(
        select(ADImport).where(ADImport.id == import_id, ADImport.engagement_id == engagement_id)
    )
    imp = result.scalar_one_or_none()
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")

    # Cascade deletes handle objects and relationships
    await db.delete(imp)


@router.get("/summary")
async def get_ad_summary(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a summary of AD data for this engagement."""
    # Get latest import
    result = await db.execute(
        select(ADImport)
        .where(ADImport.engagement_id == engagement_id)
        .order_by(ADImport.created_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    if not latest:
        return {"has_data": False}

    # Stats
    obj_result = await db.execute(
        select(ADObject.object_type, func.count(ADObject.id))
        .where(ADObject.import_id == latest.id)
        .group_by(ADObject.object_type)
    )
    type_counts = dict(obj_result.all())

    rel_result = await db.execute(
        select(ADRelationship.relationship_type, func.count(ADRelationship.id))
        .where(ADRelationship.import_id == latest.id)
        .group_by(ADRelationship.relationship_type)
    )
    rel_counts = dict(rel_result.all())

    # Key findings
    kerb_count = rel_counts.get("Kerberoastable", 0)
    asrep_count = rel_counts.get("ASREPRoastable", 0)

    # Unconstrained delegation
    uncon_result = await db.execute(
        select(func.count(ADObject.id))
        .where(ADObject.import_id == latest.id)
    )

    return {
        "has_data": True,
        "import_id": latest.id,
        "domain": latest.domain,
        "object_counts": type_counts,
        "relationship_counts": rel_counts,
        "kerberoastable": kerb_count,
        "asrep_roastable": asrep_count,
    }


@router.get("/paths")
async def list_ad_attack_paths(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get latest import
    result = await db.execute(
        select(ADImport)
        .where(ADImport.engagement_id == engagement_id)
        .order_by(ADImport.created_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    if not latest:
        return []

    path_result = await db.execute(
        select(ADAttackPath)
        .where(ADAttackPath.import_id == latest.id)
        .order_by(ADAttackPath.created_at.desc())
    )
    paths = path_result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "risk_level": p.risk_level,
            "path_nodes": p.path_nodes,
            "remediation": p.remediation,
        }
        for p in paths
    ]


@router.post("/analyze")
async def analyze_ad_paths(
    engagement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """AI-powered analysis of AD data to find critical attack paths."""
    # Get latest import
    result = await db.execute(
        select(ADImport)
        .where(ADImport.engagement_id == engagement_id)
        .order_by(ADImport.created_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    if not latest:
        raise HTTPException(status_code=400, detail="No SharpHound data imported. Upload a ZIP first.")

    # Load objects and relationships
    obj_result = await db.execute(
        select(ADObject).where(ADObject.import_id == latest.id)
    )
    objects = obj_result.scalars().all()

    rel_result = await db.execute(
        select(ADRelationship).where(ADRelationship.import_id == latest.id)
    )
    relationships = rel_result.scalars().all()

    # Build summary for AI
    from app.ad.parser import ParseResult
    pr = ParseResult()
    pr.domain = latest.domain
    pr.objects = [
        {
            "object_id": o.object_id,
            "name": o.name,
            "object_type": o.object_type,
            "domain": o.domain,
            "enabled": o.enabled,
            "properties": o.properties or {},
        }
        for o in objects
    ]
    pr.relationships = [
        {
            "source_id": r.source_id,
            "target_id": r.target_id,
            "relationship_type": r.relationship_type,
            "is_inherited": r.is_inherited,
        }
        for r in relationships
    ]

    summary = build_ad_summary(pr)

    # Delete existing paths for this import
    await db.execute(delete(ADAttackPath).where(ADAttackPath.import_id == latest.id))

    # AI analysis
    provider = get_provider()
    try:
        response = await provider.complete(
            system_prompt=AD_ANALYSIS_PROMPT,
            user_message=summary,
            max_tokens=8192,
            temperature=0.2,
        )
    except Exception as e:
        logger.error("AI provider error during AD analysis: %s", e)
        raise HTTPException(status_code=502, detail=f"AI provider error: {e}")

    # Parse response — handle common LLM output quirks
    try:
        cleaned = response.strip()
        # Strip markdown code fences
        if "```" in cleaned:
            # Find content between first ``` and last ```
            start = cleaned.find("```")
            end = cleaned.rfind("```")
            if start != end:
                inner = cleaned[start:end]
                # Remove the opening fence line (```json or ```)
                inner = inner.split("\n", 1)[1] if "\n" in inner else inner[3:]
                cleaned = inner.strip()
            else:
                cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        # Try to find JSON array in the response
        if not cleaned.startswith("["):
            bracket_start = cleaned.find("[")
            if bracket_start != -1:
                # Find the matching closing bracket
                depth = 0
                for i in range(bracket_start, len(cleaned)):
                    if cleaned[i] == "[":
                        depth += 1
                    elif cleaned[i] == "]":
                        depth -= 1
                        if depth == 0:
                            cleaned = cleaned[bracket_start:i+1]
                            break
        paths_data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("Failed to parse AD analysis response: %s", response[:500])
        raise HTTPException(status_code=502, detail="AI returned invalid JSON")

    # Store paths and create findings
    created = []
    findings_created = 0
    for pd in paths_data:
        path = ADAttackPath(
            import_id=latest.id,
            name=pd.get("name", "Unnamed Path"),
            description=pd.get("description"),
            risk_level=pd.get("risk_level"),
            path_nodes=pd.get("path_nodes"),
            remediation=pd.get("remediation"),
        )
        db.add(path)
        await db.flush()
        created.append({
            "id": path.id,
            "name": path.name,
            "description": path.description,
            "risk_level": path.risk_level,
            "path_nodes": path.path_nodes,
            "remediation": path.remediation,
        })

        # Create a finding for each attack path
        from app.engagements.models import Finding
        risk_to_severity = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
        risk_to_cvss = {"critical": 9.8, "high": 8.5, "medium": 6.5, "low": 3.5}
        sev = risk_to_severity.get(pd.get("risk_level", "medium"), "medium")
        cvss = risk_to_cvss.get(pd.get("risk_level", "medium"), 6.5)

        # Build evidence from path nodes
        evidence_lines = ["Attack Path Chain:"]
        for i, node in enumerate(pd.get("path_nodes", [])):
            evidence_lines.append(f"  {i+1}. [{node.get('type', '?').upper()}] {node.get('name', '?')} -- {node.get('technique', '')}")

        # Build affected hosts from computer nodes
        hosts = [n.get("name", "") for n in pd.get("path_nodes", []) if n.get("type") in ("computer", "domain")]

        finding = Finding(
            engagement_id=engagement_id,
            title=f"AD: {pd.get('name', 'Attack Path')}",
            description=pd.get("description"),
            severity=sev,
            cvss_score=cvss,
            affected_hosts=", ".join(hosts) if hosts else latest.domain,
            evidence="\n".join(evidence_lines),
            remediation=pd.get("remediation"),
            source="ai_generated",
            created_by=current_user.id,
        )
        db.add(finding)
        findings_created += 1

    await db.flush()

    logger.info("AD analysis: %d paths, %d findings for domain %s", len(created), findings_created, latest.domain)
    return created
