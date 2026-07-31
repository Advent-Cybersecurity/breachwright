"""Single source of truth for the Breachwright application version."""

import re


APP_VERSION = "2.2.0"

_SEMVER = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)


def _parse_version(version: str):
    match = _SEMVER.fullmatch(version.strip())
    if not match:
        return None
    core = tuple(int(match.group(name)) for name in ("major", "minor", "patch"))
    prerelease = match.group("prerelease")
    if prerelease is None:
        return core, None
    identifiers = tuple(
        (0, int(identifier)) if identifier.isdigit() else (1, identifier)
        for identifier in prerelease.split(".")
    )
    return core, identifiers


def is_newer_version(latest: str, current: str) -> bool:
    """Return true only when latest has greater semantic-version precedence."""
    latest_parsed = _parse_version(latest)
    current_parsed = _parse_version(current)
    if latest_parsed is None or current_parsed is None:
        return False

    latest_core, latest_prerelease = latest_parsed
    current_core, current_prerelease = current_parsed
    if latest_core != current_core:
        return latest_core > current_core
    if latest_prerelease is None:
        return current_prerelease is not None
    if current_prerelease is None:
        return False
    return latest_prerelease > current_prerelease
