"""SharpHound/BloodHound output parser.

Parses the ZIP files produced by SharpHound (.exe) or BloodHound.py
into normalized AD objects and relationships.

Supports:
- SharpHound (Windows collector): *_computers.json, *_users.json, etc.
- BloodHound.py (Python collector): similar JSON structure
- BloodHound CE format (newer structure with "data" and "meta" keys)
"""
import json
import zipfile
import logging
import os
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)

MAX_ZIP_ENTRIES = 1000
MAX_JSON_MEMBER_SIZE = 100 * 1024 * 1024
MAX_TOTAL_JSON_SIZE = 500 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250

# Relationship types that matter for attack path analysis
INTERESTING_ACES = {
    "GenericAll", "GenericWrite", "WriteOwner", "WriteDacl",
    "ForceChangePassword", "AddMember", "AllExtendedRights",
    "Owns", "DCSync", "GetChanges", "GetChangesAll",
    "ReadLAPSPassword", "ReadGMSAPassword",
    "AddSelf", "AddAllowedToAct", "AllowedToAct",
    "WriteAccountRestrictions",
}

HIGH_VALUE_GROUPS = {
    "DOMAIN ADMINS", "ENTERPRISE ADMINS", "ADMINISTRATORS",
    "ACCOUNT OPERATORS", "BACKUP OPERATORS", "SERVER OPERATORS",
    "DOMAIN CONTROLLERS", "SCHEMA ADMINS", "KEY ADMINS",
    "ENTERPRISE KEY ADMINS", "DNSADMINS",
}


class ParseResult:
    def __init__(self):
        self.objects = []         # List of dicts
        self.relationships = []   # List of dicts
        self.domain = None
        self.stats = {
            "users": 0, "computers": 0, "groups": 0,
            "domains": 0, "ous": 0, "gpos": 0,
            "sessions": 0, "relationships": 0,
        }


def parse_sharphound_zip(zip_data: bytes) -> ParseResult:
    """Parse a SharpHound/BloodHound ZIP file."""
    result = ParseResult()

    try:
        zf = zipfile.ZipFile(BytesIO(zip_data))
    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP file")

    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ValueError("ZIP contains too many files")
    json_infos = [info for info in infos if info.filename.lower().endswith(".json")]
    total_size = sum(info.file_size for info in json_infos)
    if total_size > MAX_TOTAL_JSON_SIZE:
        raise ValueError("ZIP expands beyond the 500MB safety limit")

    for info in json_infos:
        name = info.filename
        lower = name.lower()
        if info.file_size > MAX_JSON_MEMBER_SIZE:
            raise ValueError(f"ZIP member is too large: {name}")
        if (
            info.file_size > 0
            and info.compress_size > 0
            and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise ValueError(f"ZIP member has an unsafe compression ratio: {name}")

        try:
            raw = zf.read(info)
            data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Could not parse %s: %s", name, e)
            continue

        # Determine file type from filename
        if "computer" in lower:
            _parse_computers(data, result)
        elif "user" in lower:
            _parse_users(data, result)
        elif "group" in lower:
            _parse_groups(data, result)
        elif "domain" in lower:
            _parse_domains(data, result)
        elif "session" in lower:
            _parse_sessions(data, result)
        elif "ou" in lower:
            _parse_ous(data, result)
        elif "gpo" in lower:
            _parse_gpos(data, result)

    result.stats["relationships"] = len(result.relationships)
    logger.info(
        "Parsed SharpHound data: %d objects, %d relationships, domain: %s",
        len(result.objects), len(result.relationships), result.domain,
    )
    return result


def _get_items(data) -> list:
    """Extract items from either CE format or legacy format."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "data" in data:
            return data["data"] if isinstance(data["data"], list) else []
        return [data]
    return []


def _extract_props(item: dict) -> dict:
    """Extract properties from an item, handling both formats."""
    props = item.get("Properties", item.get("properties", {}))
    if not isinstance(props, dict):
        props = {}
    return props


def _get_object_id(item: dict) -> Optional[str]:
    """Get the object identifier."""
    return (
        item.get("ObjectIdentifier")
        or item.get("objectid")
        or item.get("Properties", {}).get("objectid")
        or item.get("ObjectId")
    )


def _parse_computers(data, result: ParseResult):
    for item in _get_items(data):
        obj_id = _get_object_id(item)
        if not obj_id:
            continue

        props = _extract_props(item)
        name = props.get("name", "") or props.get("displayname", "") or obj_id
        domain = props.get("domain", "")

        if domain and not result.domain:
            result.domain = domain

        obj = {
            "object_id": obj_id,
            "name": name,
            "object_type": "computer",
            "domain": domain,
            "enabled": props.get("enabled", True),
            "properties": {
                "os": props.get("operatingsystem", ""),
                "unconstraineddelegation": props.get("unconstraineddelegation", False),
                "trustedtoauth": props.get("trustedtoauth", False),
                "haslaps": props.get("haslaps", False),
                "lastlogon": props.get("lastlogontimestamp", ""),
                "serviceprincipalnames": props.get("serviceprincipalnames", []),
            },
        }
        result.objects.append(obj)
        result.stats["computers"] += 1

        # Process ACEs
        _parse_aces(item, obj_id, result)

        # AllowedToDelegate
        for target in (item.get("AllowedToDelegate", []) or []):
            tid = target if isinstance(target, str) else target.get("ObjectIdentifier", "")
            if tid:
                result.relationships.append({
                    "source_id": obj_id, "target_id": tid,
                    "relationship_type": "AllowedToDelegate", "is_inherited": False,
                })

        # Sessions (HasSession)
        for session in (item.get("Sessions", {}).get("Results", []) or []):
            uid = session.get("UserSID") or session.get("ObjectIdentifier", "")
            if uid:
                result.relationships.append({
                    "source_id": obj_id, "target_id": uid,
                    "relationship_type": "HasSession", "is_inherited": False,
                })

        # LocalAdmins
        for la in (item.get("LocalAdmins", {}).get("Results", []) or []):
            sid = la.get("ObjectIdentifier", "")
            if sid:
                result.relationships.append({
                    "source_id": sid, "target_id": obj_id,
                    "relationship_type": "AdminTo", "is_inherited": False,
                })


def _parse_users(data, result: ParseResult):
    for item in _get_items(data):
        obj_id = _get_object_id(item)
        if not obj_id:
            continue

        props = _extract_props(item)
        name = props.get("name", "") or props.get("displayname", "") or obj_id
        domain = props.get("domain", "")

        if domain and not result.domain:
            result.domain = domain

        obj = {
            "object_id": obj_id,
            "name": name,
            "object_type": "user",
            "domain": domain,
            "enabled": props.get("enabled", True),
            "properties": {
                "admincount": props.get("admincount", False),
                "sensitive": props.get("sensitive", False),
                "dontreqpreauth": props.get("dontreqpreauth", False),
                "hasspn": props.get("hasspn", False),
                "passwordnotreqd": props.get("passwordnotreqd", False),
                "unconstraineddelegation": props.get("unconstraineddelegation", False),
                "pwdneverexpires": props.get("pwdneverexpires", False),
                "lastlogon": props.get("lastlogontimestamp", ""),
                "pwdlastset": props.get("pwdlastset", ""),
                "serviceprincipalnames": props.get("serviceprincipalnames", []),
            },
        }
        result.objects.append(obj)
        result.stats["users"] += 1

        _parse_aces(item, obj_id, result)

        # SPNs = Kerberoastable
        if props.get("hasspn", False) and props.get("enabled", True):
            result.relationships.append({
                "source_id": obj_id, "target_id": obj_id,
                "relationship_type": "Kerberoastable", "is_inherited": False,
            })

        # AS-REP Roastable
        if props.get("dontreqpreauth", False):
            result.relationships.append({
                "source_id": obj_id, "target_id": obj_id,
                "relationship_type": "ASREPRoastable", "is_inherited": False,
            })


def _parse_groups(data, result: ParseResult):
    for item in _get_items(data):
        obj_id = _get_object_id(item)
        if not obj_id:
            continue

        props = _extract_props(item)
        name = props.get("name", "") or obj_id
        domain = props.get("domain", "")

        is_high_value = any(hv in name.upper() for hv in HIGH_VALUE_GROUPS)

        obj = {
            "object_id": obj_id,
            "name": name,
            "object_type": "group",
            "domain": domain,
            "enabled": True,
            "properties": {
                "admincount": props.get("admincount", False),
                "highvalue": is_high_value or props.get("highvalue", False),
            },
        }
        result.objects.append(obj)
        result.stats["groups"] += 1

        # Members
        members = item.get("Members", []) or []
        for member in members:
            mid = member.get("ObjectIdentifier", "") if isinstance(member, dict) else member
            if mid:
                result.relationships.append({
                    "source_id": mid, "target_id": obj_id,
                    "relationship_type": "MemberOf", "is_inherited": False,
                })

        _parse_aces(item, obj_id, result)


def _parse_domains(data, result: ParseResult):
    for item in _get_items(data):
        obj_id = _get_object_id(item)
        if not obj_id:
            continue

        props = _extract_props(item)
        name = props.get("name", "") or obj_id
        result.domain = name

        obj = {
            "object_id": obj_id,
            "name": name,
            "object_type": "domain",
            "domain": name,
            "enabled": True,
            "properties": {
                "functionallevel": props.get("functionallevel", ""),
            },
        }
        result.objects.append(obj)
        result.stats["domains"] += 1

        # Trusts
        for trust in (item.get("Trusts", []) or []):
            tid = trust.get("TargetDomainSid", "") or trust.get("ObjectIdentifier", "")
            tname = trust.get("TargetDomainName", "")
            ttype = trust.get("TrustDirection", 0)
            if tid:
                result.relationships.append({
                    "source_id": obj_id, "target_id": tid,
                    "relationship_type": f"TrustedBy" if ttype == 1 else "Trusts",
                    "is_inherited": False,
                })

        _parse_aces(item, obj_id, result)


def _parse_sessions(data, result: ParseResult):
    for item in _get_items(data):
        user_id = item.get("UserSID", "") or item.get("UserId", "")
        comp_id = item.get("ComputerSID", "") or item.get("ComputerId", "")
        if user_id and comp_id:
            result.relationships.append({
                "source_id": comp_id, "target_id": user_id,
                "relationship_type": "HasSession", "is_inherited": False,
            })
            result.stats["sessions"] += 1


def _parse_ous(data, result: ParseResult):
    for item in _get_items(data):
        obj_id = _get_object_id(item)
        if not obj_id:
            continue
        props = _extract_props(item)
        obj = {
            "object_id": obj_id,
            "name": props.get("name", "") or obj_id,
            "object_type": "ou",
            "domain": props.get("domain", ""),
            "enabled": True,
            "properties": {},
        }
        result.objects.append(obj)
        result.stats["ous"] += 1
        _parse_aces(item, obj_id, result)


def _parse_gpos(data, result: ParseResult):
    for item in _get_items(data):
        obj_id = _get_object_id(item)
        if not obj_id:
            continue
        props = _extract_props(item)
        obj = {
            "object_id": obj_id,
            "name": props.get("name", "") or obj_id,
            "object_type": "gpo",
            "domain": props.get("domain", ""),
            "enabled": True,
            "properties": {},
        }
        result.objects.append(obj)
        result.stats["gpos"] += 1
        _parse_aces(item, obj_id, result)


def _parse_aces(item: dict, target_id: str, result: ParseResult):
    """Parse ACE entries for interesting permissions."""
    aces = item.get("Aces", []) or []
    for ace in aces:
        right = ace.get("RightName", "") or ace.get("Right", "")
        principal = ace.get("PrincipalSID", "") or ace.get("PrincipalId", "")
        inherited = ace.get("IsInherited", False)

        if right in INTERESTING_ACES and principal:
            result.relationships.append({
                "source_id": principal,
                "target_id": target_id,
                "relationship_type": right,
                "is_inherited": inherited,
            })


def build_ad_summary(result: ParseResult) -> str:
    """Build a text summary of AD data for AI analysis."""
    lines = [f"Active Directory Domain: {result.domain or 'Unknown'}"]
    lines.append(f"Objects: {len(result.objects)} ({result.stats})")
    lines.append(f"Relationships: {len(result.relationships)}")
    lines.append("")

    # High-value targets
    hv_groups = [o for o in result.objects if o["object_type"] == "group"
                 and o.get("properties", {}).get("highvalue")]
    if hv_groups:
        lines.append("== High-Value Groups ==")
        for g in hv_groups:
            lines.append(f"  {g['name']}")

    # Kerberoastable users
    kerb = [r for r in result.relationships if r["relationship_type"] == "Kerberoastable"]
    if kerb:
        kerb_users = []
        for r in kerb:
            u = next((o for o in result.objects if o["object_id"] == r["source_id"]), None)
            if u:
                kerb_users.append(u["name"])
        if kerb_users:
            lines.append(f"\n== Kerberoastable Users ({len(kerb_users)}) ==")
            for name in kerb_users[:20]:
                lines.append(f"  {name}")

    # AS-REP Roastable
    asrep = [r for r in result.relationships if r["relationship_type"] == "ASREPRoastable"]
    if asrep:
        asrep_users = []
        for r in asrep:
            u = next((o for o in result.objects if o["object_id"] == r["source_id"]), None)
            if u:
                asrep_users.append(u["name"])
        if asrep_users:
            lines.append(f"\n== AS-REP Roastable Users ({len(asrep_users)}) ==")
            for name in asrep_users[:20]:
                lines.append(f"  {name}")

    # Unconstrained delegation
    uncon = [o for o in result.objects if o.get("properties", {}).get("unconstraineddelegation")]
    if uncon:
        lines.append(f"\n== Unconstrained Delegation ({len(uncon)}) ==")
        for o in uncon[:20]:
            lines.append(f"  {o['name']} ({o['object_type']})")

    # Interesting ACE relationships (non-inherited)
    ace_rels = [r for r in result.relationships
                if r["relationship_type"] in INTERESTING_ACES and not r["is_inherited"]]
    if ace_rels:
        lines.append(f"\n== Interesting ACL Relationships ({len(ace_rels)}) ==")
        # Group by relationship type
        by_type = {}
        for r in ace_rels:
            by_type.setdefault(r["relationship_type"], []).append(r)
        for rtype, rels in sorted(by_type.items(), key=lambda x: -len(x[1])):
            lines.append(f"\n  {rtype} ({len(rels)}):")
            for r in rels[:10]:
                src = next((o for o in result.objects if o["object_id"] == r["source_id"]), None)
                tgt = next((o for o in result.objects if o["object_id"] == r["target_id"]), None)
                src_name = src["name"] if src else r["source_id"][:20]
                tgt_name = tgt["name"] if tgt else r["target_id"][:20]
                lines.append(f"    {src_name} -> {tgt_name}")

    # MemberOf for high-value groups
    if hv_groups:
        lines.append("\n== High-Value Group Membership ==")
        for g in hv_groups:
            members = [r for r in result.relationships
                       if r["target_id"] == g["object_id"] and r["relationship_type"] == "MemberOf"]
            if members:
                lines.append(f"\n  {g['name']} ({len(members)} members):")
                for m in members[:15]:
                    src = next((o for o in result.objects if o["object_id"] == m["source_id"]), None)
                    if src:
                        lines.append(f"    {src['name']} ({src['object_type']})")

    # AdminTo relationships
    admin_rels = [r for r in result.relationships if r["relationship_type"] == "AdminTo"]
    if admin_rels:
        lines.append(f"\n== Local Admin Access ({len(admin_rels)}) ==")
        for r in admin_rels[:20]:
            src = next((o for o in result.objects if o["object_id"] == r["source_id"]), None)
            tgt = next((o for o in result.objects if o["object_id"] == r["target_id"]), None)
            if src and tgt:
                lines.append(f"  {src['name']} -> AdminTo -> {tgt['name']}")

    return "\n".join(lines)
