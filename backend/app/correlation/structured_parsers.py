"""Structured Scan Parsers.

Unlike the text parsers in analysis/parsers.py, these extract normalized
data structures from scan outputs. Each parser returns a list of HostRecord
dicts that the correlation engine can cross-reference.

A HostRecord looks like:
{
    "host": "10.0.0.1",
    "hostnames": ["dc01.corp.local"],
    "os": "Windows Server 2019",
    "ports": [
        {
            "port": 445,
            "protocol": "tcp",
            "state": "open",
            "service": "microsoft-ds",
            "product": "Windows Server 2019",
            "version": "10.0",
            "scripts": {"smb-signing": "disabled"},
        }
    ],
    "vulns": [
        {
            "title": "SMB Signing Disabled",
            "severity": "medium",
            "cvss": 5.3,
            "port": 445,
            "cve": None,
            "description": "...",
            "solution": "...",
            "plugin_id": "57608",
            "source": "nessus",
        }
    ],
    "source": "nmap",
}
"""
import re
import xml.etree.ElementTree as ET
import logging
import json
import math
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _safe_port(value, default=None):
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    return port if 0 <= port <= 65535 else default


def _safe_cvss(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if math.isfinite(score) and 0 <= score <= 10 else None


def parse_nmap_structured(content: str) -> list[dict]:
    """Parse nmap XML into structured HostRecords."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return _parse_nmap_text(content)

    hosts = []
    for host_el in root.findall(".//host"):
        status_el = host_el.find("status")
        if status_el is not None and status_el.get("state") != "up":
            continue

        addr_el = host_el.find("address")
        if addr_el is None:
            continue

        host = {
            "host": addr_el.get("addr", "unknown"),
            "hostnames": [],
            "os": None,
            "ports": [],
            "vulns": [],
            "source": "nmap",
        }

        # Hostnames
        for hn in host_el.findall(".//hostname"):
            name = hn.get("name", "")
            if name:
                host["hostnames"].append(name)

        # OS
        osmatch = host_el.find(".//osmatch")
        if osmatch is not None:
            host["os"] = osmatch.get("name", "")

        # Ports
        for port_el in host_el.findall(".//port"):
            state_el = port_el.find("state")
            state = state_el.get("state", "closed") if state_el is not None else "closed"
            if state not in ("open", "open|filtered"):
                continue

            service_el = port_el.find("service")
            port_number = _safe_port(port_el.get("portid"))
            if port_number is None:
                continue
            port_rec = {
                "port": port_number,
                "protocol": port_el.get("protocol", "tcp"),
                "state": state,
                "service": service_el.get("name", "unknown") if service_el is not None else "unknown",
                "product": service_el.get("product", "") if service_el is not None else "",
                "version": service_el.get("version", "") if service_el is not None else "",
                "scripts": {},
            }

            # NSE scripts (these often indicate vulns)
            for script in port_el.findall("script"):
                sid = script.get("id", "")
                output = script.get("output", "").strip()
                if sid:
                    port_rec["scripts"][sid] = output[:500]

                    # Extract vulns from known NSE scripts
                    vuln = _nse_to_vuln(sid, output, port_rec["port"])
                    if vuln:
                        host["vulns"].append(vuln)

            host["ports"].append(port_rec)

        # Host-level scripts
        for script in host_el.findall(".//hostscript/script"):
            sid = script.get("id", "")
            output = script.get("output", "").strip()
            vuln = _nse_to_vuln(sid, output, None)
            if vuln:
                host["vulns"].append(vuln)

        hosts.append(host)

    return hosts


def _nse_to_vuln(script_id: str, output: str, port: int) -> dict | None:
    """Convert known NSE script results to vulnerability records."""
    vuln_scripts = {
        "smb-vuln-ms17-010": ("MS17-010 EternalBlue RCE", "critical", 9.8, "CVE-2017-0144"),
        "smb-vuln-ms08-067": ("MS08-067 NetAPI RCE", "critical", 10.0, "CVE-2008-4250"),
        "smb2-security-mode": None,  # Check output
        "ssl-heartbleed": ("Heartbleed (OpenSSL)", "critical", 9.1, "CVE-2014-0160"),
        "ssl-poodle": ("POODLE SSLv3", "medium", 5.9, "CVE-2014-3566"),
        "ssl-cert": None,  # Check for expiry
        "http-vuln-cve2017-5638": ("Apache Struts2 RCE", "critical", 10.0, "CVE-2017-5638"),
    }

    if script_id in vuln_scripts:
        preset = vuln_scripts[script_id]
        if preset:
            return {
                "title": preset[0], "severity": preset[1], "cvss": preset[2],
                "cve": preset[3], "port": port, "description": output[:300],
                "solution": "", "plugin_id": script_id, "source": "nmap_nse",
            }

    # SMB signing check
    if script_id == "smb2-security-mode" and "not required" in output.lower():
        return {
            "title": "SMB Signing Not Required", "severity": "medium", "cvss": 5.3,
            "cve": None, "port": port or 445, "description": output[:300],
            "solution": "Enable SMB signing via Group Policy",
            "plugin_id": script_id, "source": "nmap_nse",
        }

    # Expired SSL cert
    if script_id == "ssl-cert" and "expired" in output.lower():
        return {
            "title": "Expired SSL/TLS Certificate", "severity": "medium", "cvss": 5.0,
            "cve": None, "port": port, "description": output[:300],
            "solution": "Renew the SSL/TLS certificate",
            "plugin_id": script_id, "source": "nmap_nse",
        }

    return None


def _parse_nmap_text(content: str) -> list[dict]:
    """Fallback parser for nmap text (-oN) output."""
    hosts = []
    current_host = None

    for line in content.split("\n"):
        # Host line: "Nmap scan report for 10.0.0.1"
        m = re.match(r"Nmap scan report for\s+(\S+)(?:\s+\((\S+)\))?", line)
        if m:
            if current_host:
                hosts.append(current_host)
            ip = m.group(2) or m.group(1)
            hostname = m.group(1) if m.group(2) else None
            current_host = {
                "host": ip, "hostnames": [hostname] if hostname else [],
                "os": None, "ports": [], "vulns": [], "source": "nmap",
            }
            continue

        # Port line: "445/tcp  open  microsoft-ds"
        m = re.match(r"(\d+)/(tcp|udp)\s+(open|open\|filtered)\s+(\S+)(?:\s+(.*))?", line.strip())
        if m and current_host:
            port_number = _safe_port(m.group(1))
            if port_number is None:
                continue
            current_host["ports"].append({
                "port": port_number, "protocol": m.group(2), "state": m.group(3),
                "service": m.group(4), "product": m.group(5) or "", "version": "",
                "scripts": {},
            })

    if current_host:
        hosts.append(current_host)

    return hosts


def parse_nessus_structured(content: str) -> list[dict]:
    """Parse Nessus .nessus XML into structured HostRecords."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    hosts = []
    sev_map = {"0": "info", "1": "low", "2": "medium", "3": "high", "4": "critical"}

    for report_host in root.findall(".//{*}ReportHost"):
        host = {
            "host": report_host.get("name") or "unknown",
            "hostnames": [],
            "os": None,
            "ports": [],
            "vulns": [],
            "source": "nessus",
        }

        # Host properties
        seen_ports = set()
        for tag in report_host.findall(".//{*}tag"):
            tag_name = tag.get("name", "")
            if tag_name == "host-ip" and tag.text:
                host["host"] = tag.text
            elif tag_name in ("host-fqdn",) and tag.text:
                host["hostnames"].append(tag.text)
            elif tag_name in ("operating-system", "os") and tag.text:
                host["os"] = tag.text

        # Report items
        for item in report_host.findall(".//{*}ReportItem"):
            port_num = _safe_port(item.get("port"), 0)
            protocol = item.get("protocol") or "tcp"
            svc_name = item.get("svc_name", "")
            severity = sev_map.get(item.get("severity", "0"), "info")
            plugin_name = item.get("pluginName", "")
            plugin_id = item.get("pluginID", "")

            # Track ports
            port_key = (port_num, protocol)
            if port_num > 0 and port_key not in seen_ports:
                seen_ports.add(port_key)
                host["ports"].append({
                    "port": port_num, "protocol": protocol, "state": "open",
                    "service": svc_name, "product": "", "version": "",
                    "scripts": {},
                })

            # Skip pure informational
            if severity == "info":
                continue

            # Extract fields
            def _get_text(field):
                ns = item.tag.split('}')[0][1:] if '}' in item.tag else ''
                el = item.find(f"{{{ns}}}{field}") if ns else item.find(field)
                return el.text.strip() if el is not None and el.text else ""

            cve = _get_text("cve")
            cvss_text = _get_text("cvss3_base_score") or _get_text("cvss_base_score")

            host["vulns"].append({
                "title": plugin_name,
                "severity": severity,
                "cvss": _safe_cvss(cvss_text),
                "cve": cve or None,
                "port": port_num,
                "description": _get_text("description")[:500],
                "solution": _get_text("solution")[:500],
                "plugin_id": plugin_id,
                "source": "nessus",
            })

        hosts.append(host)

    return hosts


def parse_nuclei_structured(content: str) -> list[dict]:
    """Parse nuclei text output into structured HostRecords.

    Nuclei output format (per line):
    [template-id] [protocol] [severity] host:port [matched-at] [extra-info]
    Or JSON lines if run with -json.
    """
    import json as _json

    hosts_map = {}

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Try JSON format first
        if line.startswith("{"):
            try:
                j = _json.loads(line)
                if not isinstance(j, dict):
                    continue
                matched = str(j.get("matched-at", ""))
                raw_host = str(j.get("host", j.get("ip", "unknown")))
                try:
                    parsed_target = urlparse(matched if "://" in matched else raw_host)
                    host_str = parsed_target.hostname or raw_host
                    port = (
                        _safe_port(j.get("port"))
                        if j.get("port") is not None
                        else parsed_target.port
                    )
                except (TypeError, ValueError):
                    parsed_target = urlparse("")
                    host_str = raw_host
                    port = None
                if not port and parsed_target.scheme == "https":
                    port = 443
                elif not port and parsed_target.scheme == "http":
                    port = 80
                template_id = str(j.get("template-id", j.get("templateID", "")))
                info = j.get("info") if isinstance(j.get("info"), dict) else {}
                severity = str(info.get("severity") or "info").lower()
                if severity not in ("critical", "high", "medium", "low", "info"):
                    severity = "info"
                name = str(info.get("name") or template_id or "Nuclei observation")[:500]
                desc = str(info.get("description") or "")

                if host_str not in hosts_map:
                    hosts_map[host_str] = {
                        "host": host_str, "hostnames": [], "os": None,
                        "ports": [], "vulns": [], "source": "nuclei",
                    }

                hosts_map[host_str]["vulns"].append({
                    "title": name, "severity": severity, "cvss": None,
                    "cve": _extract_cve(template_id), "port": port,
                    "description": desc[:500] or f"Matched at: {matched}",
                    "solution": "", "plugin_id": template_id, "source": "nuclei",
                })
                continue
            except _json.JSONDecodeError:
                pass

        # Text format: [template-id] [proto] [severity] url
        m = re.match(
            r'\[([^\]]+)\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+(\S+)',
            line,
        )
        if m:
            template_id, protocol, severity, url = m.groups()
            severity = severity.lower()

            # Extract host from URL
            host_match = re.match(r'https?://([^:/]+)', url)
            host_str = host_match.group(1) if host_match else url
            port_match = re.search(r':(\d+)', url)
            if port_match:
                port = _safe_port(port_match.group(1))
            elif url.startswith("https://"):
                port = 443
            elif url.startswith("http://"):
                port = 80
            else:
                port = None

            if host_str not in hosts_map:
                hosts_map[host_str] = {
                    "host": host_str, "hostnames": [], "os": None,
                    "ports": [], "vulns": [], "source": "nuclei",
                }

            hosts_map[host_str]["vulns"].append({
                "title": template_id.replace("-", " ").title(),
                "severity": severity if severity in ("critical", "high", "medium", "low", "info") else "info",
                "cvss": None, "cve": _extract_cve(template_id), "port": port,
                "description": f"Detected at: {url}",
                "solution": "", "plugin_id": template_id, "source": "nuclei",
            })

    return list(hosts_map.values())


def parse_burp_structured(content: str) -> list[dict]:
    """Parse Burp Suite XML export into structured HostRecords."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    hosts_map = {}
    sev_map = {"High": "high", "Medium": "medium", "Low": "low", "Information": "info"}

    for issue in root.findall(".//issue"):
        host_el = issue.find("host")
        if host_el is None:
            continue

        host_ip = host_el.get("ip") or host_el.text or "unknown"
        host_name = host_el.text or host_ip
        port = _safe_port(issue.findtext("port"), 0)

        if host_ip not in hosts_map:
            hosts_map[host_ip] = {
                "host": host_ip, "hostnames": [host_name] if host_name != host_ip else [],
                "os": None, "ports": [], "vulns": [], "source": "burp",
            }

        severity_text = issue.findtext("severity", "Information")
        severity = sev_map.get(severity_text, "info")

        if severity == "info":
            continue

        hosts_map[host_ip]["vulns"].append({
            "title": issue.findtext("name") or "Unknown Issue",
            "severity": severity,
            "cvss": None,
            "cve": None,
            "port": port,
            "description": _strip_html(issue.findtext("issueDetail", ""))[:500],
            "solution": _strip_html(issue.findtext("remediationDetail", ""))[:500],
            "plugin_id": issue.findtext("type", ""),
            "source": "burp",
        })

    return list(hosts_map.values())


def parse_sarif_structured(content: str) -> list[dict]:
    """Parse SARIF 2.1.0 results into the common HostRecord shape."""
    def as_dict(value) -> dict:
        return value if isinstance(value, dict) else {}

    def as_list(value) -> list:
        return value if isinstance(value, list) else []

    try:
        document = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(document, dict) or not isinstance(document.get("runs"), list):
        return []

    hosts_map: dict[str, dict] = {}
    level_map = {"error": "high", "warning": "medium", "note": "low", "none": "info"}
    allowed = {"critical", "high", "medium", "low", "info"}
    for run in document["runs"]:
        if not isinstance(run, dict):
            continue
        rules = {}
        driver = as_dict(as_dict(run.get("tool")).get("driver"))
        for rule in as_list(driver.get("rules")):
            if isinstance(rule, dict) and rule.get("id"):
                rules[str(rule["id"])] = rule
        tool_name = str(driver.get("name") or "sarif")
        for result in as_list(run.get("results")):
            if not isinstance(result, dict):
                continue
            rule_id = str(result.get("ruleId") or "unclassified")
            rule = as_dict(rules.get(rule_id))
            properties = {}
            properties.update(as_dict(rule.get("properties")))
            properties.update(as_dict(result.get("properties")))
            severity = str(properties.get("security-severity") or properties.get("severity") or "").lower()
            if severity not in allowed:
                try:
                    score = _safe_cvss(severity)
                    if score is None:
                        raise ValueError
                    severity = "critical" if score >= 9 else "high" if score >= 7 else "medium" if score >= 4 else "low"
                except (TypeError, ValueError):
                    severity = level_map.get(str(result.get("level") or "warning").lower(), "medium")

            message = result.get("message") or {}
            description = message.get("text") if isinstance(message, dict) else str(message)
            title = (
                result.get("title")
                or as_dict(rule.get("shortDescription")).get("text")
                or rule.get("name")
                or rule_id
            )
            locations = as_list(result.get("locations")) or [{}]
            for location in locations:
                physical = as_dict(as_dict(location).get("physicalLocation"))
                artifact = as_dict(physical.get("artifactLocation"))
                uri = str(artifact.get("uri") or "unknown")
                parsed_uri = urlparse(uri)
                host = parsed_uri.hostname or uri
                try:
                    port = parsed_uri.port if parsed_uri.hostname else None
                except ValueError:
                    port = None
                if host not in hosts_map:
                    hosts_map[host] = {
                        "host": host,
                        "hostnames": [],
                        "os": None,
                        "ports": [],
                        "vulns": [],
                        "source": tool_name,
                    }
                hosts_map[host]["vulns"].append(
                    {
                        "title": str(title)[:500],
                        "severity": severity,
                        "cvss": None,
                        "cve": _extract_cve(rule_id + " " + str(title)),
                        "port": port,
                        "description": str(description or "")[:500],
                        "solution": str(as_dict(rule.get("help")).get("text") or "")[:500],
                        "plugin_id": rule_id,
                        "source": tool_name,
                    }
                )
    return list(hosts_map.values())


def _extract_cve(text: str) -> str | None:
    """Extract CVE ID from text."""
    m = re.search(r'(CVE-\d{4}-\d+)', text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text or "")


def parse_structured(content: str, scan_type: str) -> list[dict]:
    """Route to the appropriate structured parser."""
    scan_type = scan_type.lower()
    if scan_type == "nmap":
        if content.strip().startswith("<?xml") or content.strip().startswith("<nmaprun"):
            return parse_nmap_structured(content)
        return _parse_nmap_text(content)
    elif scan_type == "nessus":
        return parse_nessus_structured(content)
    elif scan_type == "nuclei":
        return parse_nuclei_structured(content)
    elif scan_type in ("burp", "burp_xml"):
        return parse_burp_structured(content)
    elif scan_type == "sarif":
        return parse_sarif_structured(content)
    else:
        # Unknown format — return empty, let the text parser handle it
        return []
