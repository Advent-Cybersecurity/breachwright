"""Tool Output Correlation Engine.

Takes structured HostRecords from multiple scan tools and produces:
  1. A unified host map (merged ports, services, OS from all sources)
  2. Correlated vulnerabilities (same vuln from multiple tools = one finding)
  3. Confidence scores (more tools confirming = higher confidence)
  4. A pre-correlated text summary optimized for AI analysis

The flow:
  raw scans → structured parsers → correlation engine → AI analysis

This replaces the "dump all text to AI" approach with structured
cross-referencing that gives the AI a much richer, deduplicated view.
"""
import logging
import re
from difflib import SequenceMatcher
from collections import defaultdict

logger = logging.getLogger(__name__)

# How similar two vuln titles need to be to count as the same finding
TITLE_SIMILARITY_THRESHOLD = 0.70

# CVE match is always an exact correlation
# Same host + same port + similar title is a correlation
# Same host + same CVE is always a correlation regardless of title


def correlate(host_records_by_tool: dict[str, list[dict]]) -> dict:
    """Correlate scan results across multiple tools.

    Args:
        host_records_by_tool: {"nmap": [HostRecord, ...], "nessus": [...], ...}

    Returns:
        {
            "hosts": {
                "10.0.0.1": {
                    "host": "10.0.0.1",
                    "hostnames": ["dc01.corp.local"],
                    "os": "Windows Server 2019",
                    "os_sources": ["nmap", "nessus"],
                    "ports": [...merged...],
                    "sources": ["nmap", "nessus"],
                },
                ...
            },
            "findings": [
                {
                    "title": "SMB Signing Disabled",
                    "severity": "medium",
                    "cvss": 5.3,
                    "cve": None,
                    "hosts": ["10.0.0.1", "10.0.0.5"],
                    "port": 445,
                    "sources": ["nmap_nse", "nessus"],
                    "confidence": 0.95,
                    "descriptions": {"nmap_nse": "...", "nessus": "..."},
                    "solutions": {"nessus": "..."},
                    "plugin_ids": {"nmap_nse": "smb2-security-mode", "nessus": "57608"},
                },
                ...
            ],
            "stats": {
                "total_hosts": 5,
                "total_ports": 23,
                "total_raw_vulns": 48,
                "correlated_findings": 31,
                "tools_used": ["nmap", "nessus", "nuclei"],
                "multi_source_findings": 12,
            }
        }
    """
    # Phase 1: Merge hosts across tools
    merged_hosts = _merge_hosts(host_records_by_tool)

    # Phase 2: Collect all vulns with host context
    all_vulns = _collect_vulns(host_records_by_tool)

    # Phase 3: Correlate vulns into findings
    findings = _correlate_vulns(all_vulns)

    # Phase 4: Score confidence
    tools_used = list(host_records_by_tool.keys())
    for f in findings:
        f["confidence"] = _compute_confidence(f, len(tools_used))

    # Sort by severity then confidence
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: (sev_order.get(f["severity"], 4), -f["confidence"]))

    # Stable evidence identifiers let model output refer back to exact scanner
    # facts without copying or inventing provenance.
    for finding_index, finding in enumerate(findings, 1):
        finding["evidence_id"] = f"CF-{finding_index:04d}"
        for evidence_index, evidence in enumerate(finding["evidence_refs"], 1):
            evidence["id"] = f"CF-{finding_index:04d}-E{evidence_index:02d}"
    for host_index, host in enumerate(merged_hosts.values(), 1):
        for port_index, port in enumerate(host["ports"], 1):
            for evidence_index, evidence in enumerate(port.get("evidence_refs", []), 1):
                evidence["id"] = (
                    f"HP-{host_index:04d}-P{port_index:04d}-E{evidence_index:02d}"
                )

    # Stats
    total_raw = sum(
        len(v["vulns"])
        for records in host_records_by_tool.values()
        for v in records
    )
    multi_source = sum(1 for f in findings if len(f["sources"]) > 1)

    return {
        "hosts": merged_hosts,
        "findings": findings,
        "stats": {
            "total_hosts": len(merged_hosts),
            "total_ports": sum(len(h["ports"]) for h in merged_hosts.values()),
            "total_raw_vulns": total_raw,
            "correlated_findings": len(findings),
            "tools_used": tools_used,
            "multi_source_findings": multi_source,
            "dedup_ratio": round(1 - len(findings) / max(total_raw, 1), 2) if total_raw else 0,
        },
    }


def _normalize_host(host_str: str) -> str:
    """Normalize host identifier for matching."""
    return str(host_str or "unknown").strip().lower()


def _merge_hosts(by_tool: dict[str, list[dict]]) -> dict:
    """Build a unified host map from all tools."""
    merged = {}

    for tool, records in by_tool.items():
        for rec in records:
            host_key = _normalize_host(rec["host"])

            if host_key not in merged:
                merged[host_key] = {
                    "host": rec["host"],
                    "hostnames": [],
                    "os": None,
                    "os_sources": [],
                    "ports": [],
                    "sources": [],
                }

            h = merged[host_key]

            # Merge hostnames
            for hn in rec.get("hostnames", []):
                if hn and hn not in h["hostnames"]:
                    h["hostnames"].append(hn)

            # Merge OS (prefer more specific)
            if rec.get("os"):
                if not h["os"] or len(rec["os"]) > len(h["os"]):
                    h["os"] = rec["os"]
                if tool not in h["os_sources"]:
                    h["os_sources"].append(tool)

            # Track sources
            if tool not in h["sources"]:
                h["sources"].append(tool)

            # Merge ports
            existing_ports = {(p["port"], p["protocol"]) for p in h["ports"]}
            for port in rec.get("ports", []):
                port_key = (port["port"], port["protocol"])
                port_evidence = {
                    "id": "",
                    "scan_id": rec.get("_scan_id"),
                    "filename": rec.get("_scan_filename"),
                    "scan_type": rec.get("_scan_type", tool),
                    "tool": tool,
                    "host": rec["host"],
                    "port": port.get("port"),
                    "protocol": port.get("protocol"),
                    "cve": None,
                    "plugin_id": None,
                    "excerpt": (
                        f"{port.get('port')}/{port.get('protocol', 'tcp')} "
                        f"{port.get('state', 'unknown')} {port.get('service', 'unknown')} "
                        f"{port.get('product', '')} {port.get('version', '')}"
                    ).strip()[:2000],
                }
                if port_key not in existing_ports:
                    stored_port = dict(port)
                    stored_port["evidence_refs"] = [port_evidence]
                    h["ports"].append(stored_port)
                    existing_ports.add(port_key)
                else:
                    # Update existing port with richer info
                    for ep in h["ports"]:
                        if ep["port"] == port["port"] and ep["protocol"] == port["protocol"]:
                            if port.get("product") and not ep.get("product"):
                                ep["product"] = port["product"]
                            if port.get("version") and not ep.get("version"):
                                ep["version"] = port["version"]
                            if port.get("scripts"):
                                ep.setdefault("scripts", {}).update(port["scripts"])
                            ep.setdefault("evidence_refs", []).append(port_evidence)
                            break

    # Sort ports
    for h in merged.values():
        h["ports"].sort(key=lambda p: p["port"])

    return merged


def _collect_vulns(by_tool: dict[str, list[dict]]) -> list[dict]:
    """Flatten all vulns with their host context."""
    vulns = []
    for tool, records in by_tool.items():
        for rec in records:
            host = rec["host"]
            for v in rec.get("vulns", []):
                vulns.append({**v, "_host": host})
    return vulns


def _normalize_title(title: str) -> str:
    """Normalize vuln title for matching."""
    t = str(title or "Untitled finding").lower().strip()
    # Remove common noise
    for prefix in ("vulnerability:", "vuln:", "finding:"):
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
    t = re.sub(r'\s+', ' ', t)
    return t


def _titles_similar(a: str, b: str) -> float:
    """Compute title similarity score."""
    na, nb = _normalize_title(a), _normalize_title(b)
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    return SequenceMatcher(None, na, nb).ratio()


def _correlate_vulns(all_vulns: list[dict]) -> list[dict]:
    """Group vulns into correlated findings."""
    findings = []

    for vuln in all_vulns:
        matched = False
        for finding in findings:
            if _should_merge(finding, vuln):
                _merge_into(finding, vuln)
                matched = True
                break

        if not matched:
            findings.append(_new_finding(vuln))

    return findings


def _should_merge(finding: dict, vuln: dict) -> bool:
    """Determine if a vuln should merge into an existing finding."""
    # Same CVE = always merge (strongest signal)
    if finding.get("cve") and vuln.get("cve"):
        if finding["cve"].upper() == vuln["cve"].upper():
            return True

    # Same host + same port + similar title
    if vuln["_host"] in finding["hosts"] or _hosts_overlap(finding["hosts"], vuln["_host"]):
        if vuln.get("port") and finding.get("port"):
            if vuln["port"] == finding["port"]:
                if _titles_similar(finding["title"], vuln["title"]) >= TITLE_SIMILARITY_THRESHOLD:
                    return True

    # Very similar title regardless of host (same vuln type on different hosts)
    if _titles_similar(finding["title"], vuln["title"]) >= 0.85:
        return True

    return False


def _hosts_overlap(finding_hosts: list, vuln_host: str) -> bool:
    """Check if vuln host matches any finding host (normalized)."""
    nh = _normalize_host(vuln_host)
    return any(_normalize_host(h) == nh for h in finding_hosts)


def _new_finding(vuln: dict) -> dict:
    """Create a new finding from a vuln."""
    source = vuln.get("source", "unknown")
    return {
        "title": vuln["title"],
        "severity": vuln.get("severity", "info"),
        "cvss": vuln.get("cvss"),
        "cve": vuln.get("cve"),
        "hosts": [vuln["_host"]],
        "port": vuln.get("port"),
        "sources": [source],
        "confidence": 0.5,
        "descriptions": {source: vuln.get("description", "")},
        "solutions": {source: vuln.get("solution", "")} if vuln.get("solution") else {},
        "plugin_ids": {source: vuln.get("plugin_id", "")} if vuln.get("plugin_id") else {},
        "evidence_refs": [_evidence_ref(vuln)],
    }


def _evidence_ref(vuln: dict) -> dict:
    """Create a bounded, serializable pointer to a scanner observation."""
    return {
        "id": "",
        "scan_id": vuln.get("_scan_id"),
        "filename": vuln.get("_scan_filename"),
        "scan_type": vuln.get("_scan_type"),
        "tool": vuln.get("source", "unknown"),
        "host": vuln.get("_host"),
        "port": vuln.get("port"),
        "cve": vuln.get("cve"),
        "plugin_id": vuln.get("plugin_id"),
        "excerpt": (vuln.get("description") or vuln.get("title") or "")[:2000],
    }


def _merge_into(finding: dict, vuln: dict):
    """Merge a vuln into an existing finding."""
    source = vuln.get("source", "unknown")

    # Add host
    if vuln["_host"] not in finding["hosts"]:
        finding["hosts"].append(vuln["_host"])

    # Add source
    if source not in finding["sources"]:
        finding["sources"].append(source)

    # Upgrade severity
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    if sev_order.get(vuln.get("severity", "info"), 4) < sev_order.get(finding["severity"], 4):
        finding["severity"] = vuln["severity"]

    # Upgrade CVSS
    if (
        vuln.get("cvss") is not None
        and (
            finding["cvss"] is None
            or vuln["cvss"] > finding["cvss"]
        )
    ):
        finding["cvss"] = vuln["cvss"]

    # Set CVE if missing
    if vuln.get("cve") and not finding.get("cve"):
        finding["cve"] = vuln["cve"]

    # Merge descriptions, solutions, plugin_ids
    if vuln.get("description"):
        finding["descriptions"][source] = vuln["description"]
    if vuln.get("solution"):
        finding["solutions"][source] = vuln["solution"]
    if vuln.get("plugin_id"):
        finding["plugin_ids"][source] = vuln["plugin_id"]
    finding["evidence_refs"].append(_evidence_ref(vuln))


def _compute_confidence(finding: dict, total_tools: int) -> float:
    """Compute confidence score for a correlated finding.

    Factors:
      - Number of confirming sources (most important)
      - Has CVE reference
      - Has CVSS score
      - Number of affected hosts
    """
    score = 0.3  # Base

    # Multi-source confirmation is the strongest signal
    source_count = len(finding["sources"])
    if source_count >= 3:
        score += 0.4
    elif source_count == 2:
        score += 0.25
    elif source_count == 1:
        score += 0.1

    # CVE reference
    if finding.get("cve"):
        score += 0.15

    # CVSS score present
    if finding.get("cvss") is not None:
        score += 0.05

    # Multiple hosts affected
    if len(finding["hosts"]) > 1:
        score += 0.05

    return min(round(score, 2), 1.0)


def to_ai_prompt(correlated: dict) -> str:
    """Convert correlated results into optimized text for AI analysis.

    Instead of raw scan dumps, the AI gets a pre-correlated view:
    structured host map + deduplicated findings with multi-tool evidence.
    """
    lines = []
    stats = correlated["stats"]

    lines.append("=== CORRELATED SCAN RESULTS ===")
    lines.append(f"Tools: {', '.join(stats['tools_used'])}")
    lines.append(f"Hosts: {stats['total_hosts']} | Ports: {stats['total_ports']} | "
                 f"Raw vulns: {stats['total_raw_vulns']} → Correlated: {stats['correlated_findings']} "
                 f"(dedup ratio: {stats['dedup_ratio']:.0%})")
    lines.append("")

    # Host map
    lines.append("=== HOST MAP ===")
    for host_key, host in correlated["hosts"].items():
        header = f"\n[{host['host']}]"
        if host["hostnames"]:
            header += f" ({', '.join(host['hostnames'])})"
        if host["os"]:
            header += f" — {host['os']}"
        header += f"  [sources: {', '.join(host['sources'])}]"
        lines.append(header)

        for p in host["ports"]:
            svc = p["service"]
            if p.get("product"):
                svc += f" ({p['product']}"
                if p.get("version"):
                    svc += f" {p['version']}"
                svc += ")"
            evidence_ids = ", ".join(
                ref["id"] for ref in p.get("evidence_refs", []) if ref.get("id")
            )
            suffix = f" [Evidence IDs: {evidence_ids}]" if evidence_ids else ""
            lines.append(f"  {p['port']}/{p['protocol']} {p['state']} {svc}{suffix}")

    lines.append("")

    # Correlated findings
    lines.append("=== CORRELATED FINDINGS ===")
    for i, f in enumerate(correlated["findings"], 1):
        conf_label = "HIGH" if f["confidence"] >= 0.7 else "MEDIUM" if f["confidence"] >= 0.5 else "LOW"
        lines.append(f"\n--- Finding {i}: {f['title']} [{f['evidence_id']}] ---")
        cvss_str = f" | CVSS: {f['cvss']}" if f.get('cvss') is not None else ""
        cve_str = f" | CVE: {f['cve']}" if f.get('cve') else ""
        lines.append(f"  Severity: {f['severity'].upper()}{cvss_str}{cve_str}")
        lines.append(f"  Confidence: {conf_label} ({f['confidence']}) — confirmed by {', '.join(f['sources'])}")
        lines.append(f"  Affected hosts: {', '.join(f['hosts'])}")
        if f.get("port"):
            lines.append(f"  Port: {f['port']}")

        # Include descriptions from each source
        for ref in f["evidence_refs"]:
            details = [ref["tool"]]
            if ref.get("filename"):
                details.append(ref["filename"])
            if ref.get("host"):
                details.append(str(ref["host"]))
            if ref.get("port") is not None:
                details.append(f"port {ref['port']}")
            if ref.get("cve"):
                details.append(ref["cve"])
            if ref.get("plugin_id"):
                details.append(f"plugin {ref['plugin_id']}")
            lines.append(
                f"  Evidence ID {ref['id']} ({', '.join(details)}): "
                f"{ref['excerpt'][:500]}"
            )

        # Include solutions
        for src, sol in f["solutions"].items():
            if sol:
                lines.append(f"  Remediation ({src}): {sol[:200]}")

    return "\n".join(lines)
