import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, delete, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import get_current_user, require_editor
from app.auth.models import User
from app.ad.models import ADImport, ADObject, ADRelationship, ADAttackPath
from app.engagements.models import AIFindingDraft, Engagement, Finding
from app.ad.parser import parse_sharphound_zip, build_ad_summary
from app.ad.prompts import AD_ANALYSIS_PROMPT
from app.ai.provider import get_provider
from app.ai.errors import AI_PROVIDER_FAILURE_MESSAGE
from app.ai.output_validation import validate_ai_ad_paths
from app.ai.completion import complete_validated_json
from app.ai.context import AIContextTooLarge, build_bounded_untrusted_context

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
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Expected a ZIP file (SharpHound/BloodHound output)")

    content = await file.read(100 * 1024 * 1024 + 1)
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
            "evidence_refs": p.evidence_refs or [],
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
    """Produce grounded AD paths and reviewable finding proposals."""
    result = await db.execute(
        select(ADImport)
        .where(ADImport.engagement_id == engagement_id)
        .order_by(ADImport.created_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    if not latest:
        raise HTTPException(
            status_code=400,
            detail="No SharpHound data imported. Upload a ZIP first.",
        )

    objects = (
        await db.execute(select(ADObject).where(ADObject.import_id == latest.id))
    ).scalars().all()
    relationships = (
        await db.execute(
            select(ADRelationship).where(ADRelationship.import_id == latest.id)
        )
    ).scalars().all()

    from app.ad.parser import ParseResult

    parsed = ParseResult()
    parsed.domain = latest.domain
    parsed.objects = [
        {
            "object_id": item.object_id,
            "name": item.name,
            "object_type": item.object_type,
            "domain": item.domain,
            "enabled": item.enabled,
            "properties": item.properties or {},
        }
        for item in objects
    ]
    parsed.relationships = [
        {
            "source_id": item.source_id,
            "target_id": item.target_id,
            "relationship_type": item.relationship_type,
            "is_inherited": item.is_inherited,
        }
        for item in relationships
    ]

    names_by_id = {item.object_id: item.name for item in objects}
    object_names = {item.name for item in objects}
    evidence_catalog: dict[str, dict] = {}
    evidence_lines = ["", "=== EVIDENCE IDS ==="]
    for index, item in enumerate(objects, 1):
        evidence_id = f"ADOBJ-{index:05d}"
        ref = {
            "id": evidence_id,
            "import_id": latest.id,
            "filename": latest.filename,
            "type": "ad_object",
            "object_id": item.object_id,
            "name": item.name,
            "object_type": item.object_type,
            "excerpt": f"{item.object_type}: {item.name} ({item.object_id})",
        }
        evidence_catalog[evidence_id] = ref
        evidence_lines.append(f"[{evidence_id}] {ref['excerpt']}")
    for index, item in enumerate(relationships, 1):
        evidence_id = f"ADREL-{index:05d}"
        source_name = names_by_id.get(item.source_id, item.source_id)
        target_name = names_by_id.get(item.target_id, item.target_id)
        ref = {
            "id": evidence_id,
            "import_id": latest.id,
            "filename": latest.filename,
            "type": "ad_relationship",
            "source": source_name,
            "target": target_name,
            "relationship_type": item.relationship_type,
            "excerpt": f"{source_name} --{item.relationship_type}--> {target_name}",
        }
        evidence_catalog[evidence_id] = ref
        evidence_lines.append(f"[{evidence_id}] {ref['excerpt']}")

    ad_context = build_ad_summary(parsed) + "\n" + "\n".join(evidence_lines)
    try:
        bounded_message = build_bounded_untrusted_context(
            "untrusted_ad_data",
            ad_context,
            label="Active Directory analysis data",
        )
    except AIContextTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    try:
        provider = get_provider()
        validated_paths, metadata = await complete_validated_json(
            provider,
            system_prompt=AD_ANALYSIS_PROMPT,
            user_message=bounded_message,
            validator=validate_ai_ad_paths,
            max_tokens=8192,
            temperature=0.2,
        )
    except Exception as exc:
        logger.warning("Active Directory AI request failed with %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=AI_PROVIDER_FAILURE_MESSAGE) from exc

    grounded_paths = [
        path
        for path in validated_paths
        if path.evidence_refs
        and all(ref_id in evidence_catalog for ref_id in path.evidence_refs)
        and path.path_nodes
        and all(node.name in object_names for node in path.path_nodes)
    ]
    if validated_paths and not grounded_paths:
        raise HTTPException(
            status_code=502,
            detail="AI returned Active Directory paths without valid evidence citations",
        )

    await db.execute(delete(ADAttackPath).where(ADAttackPath.import_id == latest.id))
    await db.execute(
        update(AIFindingDraft)
        .where(
            AIFindingDraft.engagement_id == engagement_id,
            AIFindingDraft.status == "pending",
            AIFindingDraft.prompt_version == "ad-analysis-v2",
        )
        .values(status="superseded", reviewed_at=datetime.now(timezone.utc))
    )

    existing_findings_result = await db.execute(
        select(Finding).where(Finding.engagement_id == engagement_id)
    )
    existing_findings = [
        {
            "id": item.id,
            "title": item.title,
            "affected_hosts": item.affected_hosts,
        }
        for item in existing_findings_result.scalars().all()
    ]
    from app.findings.dedup import find_duplicate

    created_paths = []
    draft_count = 0
    for candidate in grounded_paths:
        refs = [evidence_catalog[ref_id] for ref_id in candidate.evidence_refs]
        path_nodes = [node.model_dump(mode="json") for node in candidate.path_nodes]
        path = ADAttackPath(
            import_id=latest.id,
            name=candidate.name,
            description=candidate.description,
            risk_level=candidate.risk_level,
            path_nodes=path_nodes,
            evidence_refs=refs,
            remediation=candidate.remediation,
        )
        db.add(path)
        await db.flush()
        created_paths.append(
            {
                "id": path.id,
                "name": path.name,
                "description": path.description,
                "risk_level": path.risk_level,
                "path_nodes": path.path_nodes,
                "evidence_refs": path.evidence_refs,
                "remediation": path.remediation,
            }
        )

        hosts = sorted(
            {
                node["name"]
                for node in path_nodes
                if node["type"] in ("computer", "domain")
            }
        )
        evidence_text = "Attack Path Chain:\n" + "\n".join(
            f"  {index}. [{node['type'].upper()}] {node['name']} -- {node['technique']}"
            for index, node in enumerate(path_nodes, 1)
        )
        title = f"AD: {candidate.name}"
        affected_hosts = ", ".join(hosts) if hosts else latest.domain
        duplicate = find_duplicate(title, affected_hosts or "", existing_findings)
        confidence = 0.8 if any(ref["type"] == "ad_relationship" for ref in refs) else 0.65
        draft = AIFindingDraft(
            engagement_id=engagement_id,
            target_finding_id=duplicate["id"] if duplicate else None,
            operation="update" if duplicate else "create",
            status="pending",
            title=title,
            description=candidate.description,
            severity=candidate.risk_level,
            cvss_score={"critical": 9.8, "high": 8.5, "medium": 6.5, "low": 3.5}[
                candidate.risk_level
            ],
            affected_hosts=affected_hosts,
            evidence=evidence_text,
            remediation=candidate.remediation,
            evidence_refs=refs,
            confidence=confidence,
            provider=provider.name(),
            prompt_version="ad-analysis-v2",
            created_by=current_user.id,
        )
        db.add(draft)
        draft_count += 1

    await db.flush()
    logger.info(
        "AD analysis created %d grounded paths and %d review drafts in %d ms",
        len(created_paths),
        draft_count,
        metadata.latency_ms,
    )
    return {
        "paths": created_paths,
        "drafts_created": draft_count,
        "provider": metadata.provider,
        "latency_ms": metadata.latency_ms,
    }
