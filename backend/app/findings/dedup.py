"""Finding deduplication.

Detects duplicate findings based on title similarity and affected hosts.
Used during AI analysis to prevent creating duplicates on re-analysis.
"""
import re
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.75


def normalize_title(title: str) -> str:
    """Normalize a finding title for comparison."""
    t = title.lower().strip()
    # Remove common prefixes
    for prefix in ["ad: ", "finding: ", "vulnerability: "]:
        if t.startswith(prefix):
            t = t[len(prefix):]
    # Remove extra whitespace
    t = re.sub(r'\s+', ' ', t)
    return t


def titles_match(title1: str, title2: str) -> float:
    """Return similarity score between two finding titles (0 to 1)."""
    n1 = normalize_title(title1)
    n2 = normalize_title(title2)
    
    # Exact match
    if n1 == n2:
        return 1.0
    
    # Check if one contains the other
    if n1 in n2 or n2 in n1:
        return 0.9
    
    # SequenceMatcher similarity
    return SequenceMatcher(None, n1, n2).ratio()


def find_duplicate(new_title: str, new_hosts: str, existing_findings: list) -> dict | None:
    """Find a duplicate finding from existing findings.
    
    Returns the existing finding dict if a duplicate is found, None otherwise.
    """
    best_match = None
    best_score = 0
    
    for finding in existing_findings:
        score = titles_match(new_title, finding.get("title", ""))
        
        # Boost score if hosts also match
        if new_hosts and finding.get("affected_hosts"):
            new_hosts_set = set(h.strip().lower() for h in new_hosts.split(","))
            existing_hosts_set = set(h.strip().lower() for h in finding["affected_hosts"].split(","))
            if new_hosts_set & existing_hosts_set:
                score = min(score + 0.1, 1.0)
        
        if score > best_score:
            best_score = score
            best_match = finding
    
    if best_score >= SIMILARITY_THRESHOLD:
        logger.info("Duplicate found: '%s' matches '%s' (score: %.2f)", 
                     new_title, best_match.get("title"), best_score)
        return best_match
    
    return None


def should_update_finding(existing: dict, new_data: dict) -> dict:
    """Determine what fields to update on an existing finding.
    
    Returns dict of fields to update. Prefers higher severity,
    longer descriptions, and merges evidence.
    """
    updates = {}
    
    # Update severity if new is higher
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    existing_sev = existing.get("severity", "info")
    new_sev = new_data.get("severity", "info")
    if isinstance(existing_sev, str) and isinstance(new_sev, str):
        if sev_order.get(new_sev, 4) < sev_order.get(existing_sev, 4):
            updates["severity"] = new_sev
    
    # Update CVSS if new is higher
    new_cvss = new_data.get("cvss_score")
    existing_cvss = existing.get("cvss_score")
    if new_cvss and (not existing_cvss or float(new_cvss) > float(existing_cvss)):
        updates["cvss_score"] = new_cvss
    
    # Update description if new is longer/better
    new_desc = new_data.get("description", "")
    existing_desc = existing.get("description", "")
    if new_desc and len(new_desc) > len(existing_desc or ""):
        updates["description"] = new_desc
    
    # Merge affected hosts
    new_hosts = new_data.get("affected_hosts", "")
    existing_hosts = existing.get("affected_hosts", "")
    if new_hosts and existing_hosts:
        all_hosts = set(h.strip() for h in f"{existing_hosts},{new_hosts}".split(",") if h.strip())
        merged = ", ".join(sorted(all_hosts))
        if merged != existing_hosts:
            updates["affected_hosts"] = merged
    elif new_hosts:
        updates["affected_hosts"] = new_hosts
    
    # Update remediation if new is longer
    new_rem = new_data.get("remediation", "")
    existing_rem = existing.get("remediation", "")
    if new_rem and len(new_rem) > len(existing_rem or ""):
        updates["remediation"] = new_rem
    
    return updates
