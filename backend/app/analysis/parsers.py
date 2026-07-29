"""Scan file parsers.

Parse nmap XML, Nessus .nessus, and Burp XML into structured text
for better AI analysis results.
"""
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)


def parse_nmap_xml(content: str) -> str:
    """Parse nmap XML output into structured text."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return content  # Not valid XML, return raw

    lines = []
    scan_info = root.find(".//scaninfo")
    if scan_info is not None:
        lines.append(f"Scan type: {scan_info.get('type', 'unknown')}")
        lines.append(f"Protocol: {scan_info.get('protocol', 'unknown')}")

    for host in root.findall(".//host"):
        addr_el = host.find("address")
        addr = addr_el.get("addr", "unknown") if addr_el is not None else "unknown"
        status_el = host.find("status")
        status = status_el.get("state", "unknown") if status_el is not None else "unknown"

        lines.append(f"\n== Host: {addr} (status: {status}) ==")

        # Hostnames
        for hostname in host.findall(".//hostname"):
            lines.append(f"  Hostname: {hostname.get('name', '')} ({hostname.get('type', '')})")

        # OS detection
        for osmatch in host.findall(".//osmatch"):
            lines.append(f"  OS: {osmatch.get('name', '')} (accuracy: {osmatch.get('accuracy', '')}%)")

        # Ports
        for port in host.findall(".//port"):
            portid = port.get("portid", "?")
            protocol = port.get("protocol", "?")
            state_el = port.find("state")
            state = state_el.get("state", "?") if state_el is not None else "?"
            service_el = port.find("service")

            if service_el is not None:
                svc_name = service_el.get("name", "unknown")
                svc_product = service_el.get("product", "")
                svc_version = service_el.get("version", "")
                svc_info = f"{svc_name}"
                if svc_product:
                    svc_info += f" ({svc_product}"
                    if svc_version:
                        svc_info += f" {svc_version}"
                    svc_info += ")"
            else:
                svc_info = "unknown"

            lines.append(f"  {portid}/{protocol} {state} {svc_info}")

            # Scripts
            for script in port.findall("script"):
                script_id = script.get("id", "")
                script_output = script.get("output", "").strip()
                if script_output:
                    lines.append(f"    Script ({script_id}): {script_output[:500]}")

        # Host scripts
        for script in host.findall(".//hostscript/script"):
            script_id = script.get("id", "")
            script_output = script.get("output", "").strip()
            if script_output:
                lines.append(f"  Host Script ({script_id}): {script_output[:500]}")

    return "\n".join(lines) if lines else content


def parse_nessus(content: str) -> str:
    """Parse Nessus .nessus XML into structured text."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return content

    lines = []

    for report_host in root.findall(".//{*}ReportHost"):
        host_name = report_host.get("name", "unknown")
        lines.append(f"\n== Host: {host_name} ==")

        # Host properties
        for tag in report_host.findall(".//{*}tag"):
            tag_name = tag.get("name", "")
            if tag_name in ("operating-system", "os", "host-ip", "host-fqdn", "mac-address"):
                lines.append(f"  {tag_name}: {tag.text or ''}")

        # Report items (findings)
        for item in report_host.findall(".//{*}ReportItem"):
            port = item.get("port", "0")
            svc = item.get("svc_name", "")
            plugin_name = item.get("pluginName", "")
            severity = item.get("severity", "0")
            sev_map = {"0": "Info", "1": "Low", "2": "Medium", "3": "High", "4": "Critical"}
            sev_label = sev_map.get(severity, severity)

            if severity == "0":
                continue  # Skip informational unless needed

            lines.append(f"\n  [{sev_label}] {plugin_name} (port {port}/{svc})")

            # Key fields
            for field in ("description", "solution", "synopsis", "cvss3_base_score", "cve"):
                el = item.find(f".//{{{item.tag.split('}')[0][1:] if '}' in item.tag else ''}}}{field}")
                if el is None:
                    el = item.find(field)
                if el is not None and el.text:
                    text = el.text.strip()[:500]
                    lines.append(f"    {field}: {text}")

    return "\n".join(lines) if lines else content


def parse_scan_file(content: str, scan_type: str) -> str:
    """Parse a scan file based on its type, returning structured text."""
    if scan_type == "nmap":
        # Try XML first, fall back to raw
        if content.strip().startswith("<?xml") or content.strip().startswith("<nmaprun"):
            return parse_nmap_xml(content)
        return content  # Raw nmap text output
    elif scan_type == "nessus":
        return parse_nessus(content)
    else:
        return content  # Burp, custom, etc. pass through raw
