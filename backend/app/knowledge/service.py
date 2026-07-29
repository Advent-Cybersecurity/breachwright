"""Cross-Engagement Intelligence — Indexing & Query Engine.

Responsible for:
  1. Fingerprinting findings into canonical knowledge entries
  2. Linking new findings to existing entries (or creating new ones)
  3. Updating aggregate stats (occurrence count, client count, etc.)
  4. Querying the knowledge base for trends and patterns
  5. AI-driven insights: "what else should you test?"
"""
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, distinct, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import (
    KnowledgeEntry, FindingKnowledgeLink, FindingCategory,
)
from app.engagements.models import Finding, Engagement

logger = logging.getLogger(__name__)


# ── Fingerprinting ──────────────────────────────────────────────────────────

# Common noise words and prefixes that don't distinguish finding types
_STRIP_PREFIXES = [
    "ad:", "finding:", "vulnerability:", "vuln:", "issue:",
    "potential ", "possible ", "detected ", "identified ",
]
_STRIP_SUFFIXES = [
    " detected", " found", " identified", " present",
    " vulnerability", " issue",
]


def normalize_title(title: str) -> str:
    """Normalize a finding title to a canonical form for fingerprinting."""
    t = title.lower().strip()
    for prefix in _STRIP_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
    for suffix in _STRIP_SUFFIXES:
        if t.endswith(suffix):
            t = t[:-len(suffix)].strip()
    # Collapse whitespace, remove special chars except hyphens
    t = re.sub(r'[^\w\s-]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def compute_fingerprint(title: str, category: str = "") -> str:
    """Generate a stable fingerprint from a normalized title + category.

    Uses SHA-256 truncated to 16 hex chars. Collisions are possible but
    acceptable — the matching logic also checks title similarity.
    """
    normalized = normalize_title(title)
    raw = normalized  # Category-independent fingerprint
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def classify_category(title: str, description: str = "") -> FindingCategory:
    """Heuristic category classification based on finding text.

    This is a first pass — the AI refinement step can override it.
    """
    text = f"{title} {description}".lower()

    patterns = {
        FindingCategory.active_directory: [
            "kerberos", "ldap", "ntlm", "smb signing", "domain admin",
            "gpo", "group policy", "spn", "asreproast", "kerberoast",
            "bloodhound", "active directory", "dcsync", "golden ticket",
            "silver ticket", "pass.the.hash", "mimikatz", "lsass",
        ],
        FindingCategory.authentication: [
            "password", "credential", "brute.force", "login",
            "mfa", "multi.factor", "2fa", "default credential",
            "weak password", "password spray", "authentication bypass",
        ],
        FindingCategory.web: [
            "xss", "cross.site", "sqli", "sql injection", "csrf",
            "ssrf", "idor", "rce", "command injection", "lfi", "rfi",
            "xxe", "deserialization", "cors", "header injection",
            "open redirect", "clickjacking", "csp",
        ],
        FindingCategory.network: [
            "port", "firewall", "snmp", "ssh", "telnet", "ftp",
            "smb", "rdp", "vlan", "arp", "dns", "nfs", "nmap",
            "open port", "service exposure", "network segmentation",
        ],
        FindingCategory.cryptography: [
            "ssl", "tls", "certificate", "cipher", "encryption",
            "hashing", "sha1", "md5", "weak cipher", "expired cert",
        ],
        FindingCategory.configuration: [
            "misconfiguration", "hardening", "patch", "update",
            "eol", "end of life", "unsupported", "default config",
            "unnecessary service", "information disclosure",
        ],
        FindingCategory.cloud: [
            "aws", "azure", "gcp", "s3 bucket", "iam", "cloud",
            "serverless", "lambda", "ec2", "storage account",
        ],
        FindingCategory.wireless: [
            "wifi", "wireless", "wpa", "wep", "802.11", "rogue ap",
            "evil twin", "deauth",
        ],
    }

    for category, keywords in patterns.items():
        for kw in keywords:
            if re.search(kw.replace(".", r"\b.*\b"), text):
                return category

    return FindingCategory.other


# ── Indexing ────────────────────────────────────────────────────────────────

async def index_finding(
    db: AsyncSession,
    finding: Finding,
    engagement: Engagement,
) -> Optional[KnowledgeEntry]:
    """Index a single finding into the knowledge base.

    1. Compute fingerprint
    2. Look for existing entry with same fingerprint
    3. If found, link and update stats
    4. If not, create new entry and link
    """
    category = classify_category(finding.title, finding.description or "")
    fp = compute_fingerprint(finding.title, category.value)

    # Check for existing entry
    result = await db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.fingerprint == fp)
    )
    entry = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if entry:
        # Update existing entry stats
        entry.occurrence_count += 1
        entry.last_seen_at = now

        # Upgrade severity if this instance is worse
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        finding_sev = finding.severity.value if hasattr(finding.severity, 'value') else finding.severity
        if sev_order.get(finding_sev, 4) < sev_order.get(entry.default_severity or "info", 4):
            entry.default_severity = finding_sev

        # Upgrade CVSS if higher
        if finding.cvss_score and (not entry.default_cvss or finding.cvss_score > entry.default_cvss):
            entry.default_cvss = float(finding.cvss_score)

        # Update description/remediation if longer (likely more detailed)
        if finding.description and len(finding.description) > len(entry.description or ""):
            entry.description = finding.description
        if finding.remediation and len(finding.remediation) > len(entry.remediation or ""):
            entry.remediation = finding.remediation

    else:
        # Create new knowledge entry
        finding_sev = finding.severity.value if hasattr(finding.severity, 'value') else finding.severity
        entry = KnowledgeEntry(
            fingerprint=fp,
            canonical_title=finding.title,
            category=category,
            description=finding.description,
            remediation=finding.remediation,
            default_severity=finding_sev,
            default_cvss=float(finding.cvss_score) if finding.cvss_score else None,
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
            tags=[],
        )
        db.add(entry)
        await db.flush()

    # Check if this exact finding is already linked (idempotency)
    existing_link = await db.execute(
        select(FindingKnowledgeLink).where(
            FindingKnowledgeLink.finding_id == finding.id,
            FindingKnowledgeLink.knowledge_entry_id == entry.id,
        )
    )
    if not existing_link.scalar_one_or_none():
        link = FindingKnowledgeLink(
            finding_id=finding.id,
            knowledge_entry_id=entry.id,
            engagement_id=engagement.id,
            client_name=engagement.client_name,
            confidence=1.0,
        )
        db.add(link)

    # Recount unique clients
    client_count = await db.execute(
        select(func.count(distinct(FindingKnowledgeLink.client_name))).where(
            FindingKnowledgeLink.knowledge_entry_id == entry.id
        )
    )
    entry.unique_client_count = client_count.scalar_one() or 0

    await db.flush()
    return entry


async def index_engagement(db: AsyncSession, engagement_id: str) -> dict:
    """Index all findings from an engagement into the knowledge base.

    Returns stats: {"indexed": N, "new_entries": N, "existing_entries": N}
    """
    # Load engagement + findings
    eng_result = await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    engagement = eng_result.scalar_one_or_none()
    if not engagement:
        return {"error": "Engagement not found"}

    findings_result = await db.execute(
        select(Finding).where(Finding.engagement_id == engagement_id)
    )
    findings = findings_result.scalars().all()

    new_entries = 0
    existing_entries = 0

    for finding in findings:
        category = classify_category(finding.title, finding.description or "")
        fp = compute_fingerprint(finding.title, category.value)

        # Check if entry already exists
        check = await db.execute(
            select(KnowledgeEntry).where(KnowledgeEntry.fingerprint == fp)
        )
        existed = check.scalar_one_or_none() is not None

        await index_finding(db, finding, engagement)

        if existed:
            existing_entries += 1
        else:
            new_entries += 1

    logger.info(
        "Indexed engagement %s: %d findings → %d new, %d existing entries",
        engagement_id, len(findings), new_entries, existing_entries,
    )

    return {
        "indexed": len(findings),
        "new_entries": new_entries,
        "existing_entries": existing_entries,
    }


# ── Queries ─────────────────────────────────────────────────────────────────

async def get_trending_findings(
    db: AsyncSession,
    limit: int = 20,
    category: Optional[str] = None,
) -> list[dict]:
    """Get the most frequently occurring finding types across all engagements."""
    query = select(KnowledgeEntry).order_by(
        KnowledgeEntry.occurrence_count.desc()
    ).limit(limit)

    if category:
        query = query.where(KnowledgeEntry.category == category)

    result = await db.execute(query)
    entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "canonical_title": e.canonical_title,
            "category": e.category.value if hasattr(e.category, 'value') else e.category,
            "default_severity": e.default_severity,
            "default_cvss": e.default_cvss,
            "occurrence_count": e.occurrence_count,
            "unique_client_count": e.unique_client_count,
            "first_seen_at": e.first_seen_at.isoformat() if e.first_seen_at else None,
            "last_seen_at": e.last_seen_at.isoformat() if e.last_seen_at else None,
            "cwe_id": e.cwe_id,
            "mitre_attack_id": e.mitre_attack_id,
            "tags": e.tags or [],
        }
        for e in entries
    ]


async def get_finding_history(
    db: AsyncSession,
    knowledge_entry_id: str,
) -> dict:
    """Get the full history of a finding type across all engagements.

    Returns the knowledge entry details plus every engagement/client
    where it appeared.
    """
    entry_result = await db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id == knowledge_entry_id)
    )
    entry = entry_result.scalar_one_or_none()
    if not entry:
        return None

    links_result = await db.execute(
        select(FindingKnowledgeLink).where(
            FindingKnowledgeLink.knowledge_entry_id == knowledge_entry_id
        ).order_by(FindingKnowledgeLink.linked_at.desc())
    )
    links = links_result.scalars().all()

    return {
        "entry": {
            "id": entry.id,
            "canonical_title": entry.canonical_title,
            "category": entry.category.value if hasattr(entry.category, 'value') else entry.category,
            "description": entry.description,
            "remediation": entry.remediation,
            "default_severity": entry.default_severity,
            "default_cvss": entry.default_cvss,
            "cwe_id": entry.cwe_id,
            "mitre_attack_id": entry.mitre_attack_id,
            "occurrence_count": entry.occurrence_count,
            "unique_client_count": entry.unique_client_count,
            "tags": entry.tags or [],
        },
        "occurrences": [
            {
                "finding_id": l.finding_id,
                "engagement_id": l.engagement_id,
                "client_name": l.client_name,
                "confidence": l.confidence,
                "linked_at": l.linked_at.isoformat() if l.linked_at else None,
            }
            for l in links
        ],
    }


async def get_client_risk_profile(
    db: AsyncSession,
    client_name: str,
) -> dict:
    """Build a risk profile for a specific client across all their engagements."""
    links_result = await db.execute(
        select(FindingKnowledgeLink).where(
            FindingKnowledgeLink.client_name == client_name
        )
    )
    links = links_result.scalars().all()

    if not links:
        return {"client_name": client_name, "engagements": 0, "findings": []}

    entry_ids = list(set(l.knowledge_entry_id for l in links))
    engagement_ids = list(set(l.engagement_id for l in links))

    entries_result = await db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id.in_(entry_ids))
    )
    entries = {e.id: e for e in entries_result.scalars().all()}

    # Build severity breakdown
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    category_counts = {}
    finding_types = []

    for entry_id in entry_ids:
        entry = entries.get(entry_id)
        if not entry:
            continue
        sev = entry.default_severity or "info"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        cat = entry.category.value if hasattr(entry.category, 'value') else entry.category
        category_counts[cat] = category_counts.get(cat, 0) + 1
        finding_types.append({
            "id": entry.id,
            "title": entry.canonical_title,
            "category": cat,
            "severity": sev,
            "cvss": entry.default_cvss,
        })

    # Sort by severity
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    finding_types.sort(key=lambda f: sev_order.get(f["severity"], 4))

    return {
        "client_name": client_name,
        "engagement_count": len(engagement_ids),
        "unique_finding_types": len(entry_ids),
        "total_occurrences": len(links),
        "severity_breakdown": severity_counts,
        "category_breakdown": category_counts,
        "finding_types": finding_types,
    }


async def get_similar_environments(
    db: AsyncSession,
    engagement_id: str,
    limit: int = 10,
) -> list[dict]:
    """Find engagements with similar finding profiles.

    Uses Jaccard similarity on the set of knowledge entry IDs.
    Useful for: "Clients with similar environments also had these findings."
    """
    # Get this engagement's knowledge entry IDs
    links_result = await db.execute(
        select(FindingKnowledgeLink.knowledge_entry_id).where(
            FindingKnowledgeLink.engagement_id == engagement_id
        )
    )
    our_entries = set(r[0] for r in links_result.all())

    if not our_entries:
        return []

    # Get all other engagements that share at least one entry
    other_links = await db.execute(
        select(
            FindingKnowledgeLink.engagement_id,
            FindingKnowledgeLink.knowledge_entry_id,
            FindingKnowledgeLink.client_name,
        ).where(
            and_(
                FindingKnowledgeLink.knowledge_entry_id.in_(our_entries),
                FindingKnowledgeLink.engagement_id != engagement_id,
            )
        )
    )

    # Group by engagement
    eng_entries = {}
    eng_clients = {}
    for row in other_links.all():
        eid, kid, client = row
        eng_entries.setdefault(eid, set()).add(kid)
        eng_clients[eid] = client

    # Compute Jaccard similarity
    similarities = []
    for eid, their_entries in eng_entries.items():
        intersection = len(our_entries & their_entries)
        union = len(our_entries | their_entries)
        jaccard = intersection / union if union > 0 else 0
        similarities.append({
            "engagement_id": eid,
            "client_name": eng_clients[eid],
            "shared_findings": intersection,
            "similarity": round(jaccard, 3),
        })

    similarities.sort(key=lambda x: x["similarity"], reverse=True)
    return similarities[:limit]


async def get_recommendations(
    db: AsyncSession,
    engagement_id: str,
) -> list[dict]:
    """Recommend findings to look for based on similar engagements.

    Logic: Find similar engagements → get their finding types →
    filter out ones already in this engagement → return the remainder
    ranked by frequency.
    """
    similar = await get_similar_environments(db, engagement_id, limit=20)
    if not similar:
        return []

    # Get our current finding types
    our_links = await db.execute(
        select(FindingKnowledgeLink.knowledge_entry_id).where(
            FindingKnowledgeLink.engagement_id == engagement_id
        )
    )
    our_entry_ids = set(r[0] for r in our_links.all())

    # Get finding types from similar engagements that we DON'T have
    similar_eng_ids = [s["engagement_id"] for s in similar[:10]]
    their_links = await db.execute(
        select(
            FindingKnowledgeLink.knowledge_entry_id,
            func.count().label("freq"),
        ).where(
            and_(
                FindingKnowledgeLink.engagement_id.in_(similar_eng_ids),
                ~FindingKnowledgeLink.knowledge_entry_id.in_(our_entry_ids),
            )
        ).group_by(FindingKnowledgeLink.knowledge_entry_id)
        .order_by(func.count().desc())
        .limit(15)
    )

    recommendations = []
    for row in their_links.all():
        entry_id, freq = row
        entry_result = await db.execute(
            select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
        )
        entry = entry_result.scalar_one_or_none()
        if entry:
            recommendations.append({
                "knowledge_entry_id": entry.id,
                "title": entry.canonical_title,
                "category": entry.category.value if hasattr(entry.category, 'value') else entry.category,
                "severity": entry.default_severity,
                "cvss": entry.default_cvss,
                "seen_in_similar": freq,
                "total_occurrences": entry.occurrence_count,
                "reason": f"Found in {freq} similar engagement(s) but not in yours",
            })

    return recommendations
