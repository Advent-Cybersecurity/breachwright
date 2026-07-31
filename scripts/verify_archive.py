"""Verify a Breachwright release archive without extracting it."""

from __future__ import annotations

import argparse
import hashlib
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


REQUIRED_DOCUMENTS = {
    "Breachwright/CHANGELOG.md",
    "Breachwright/LICENSE",
    "Breachwright/NOTICE",
    "Breachwright/README.md",
    "Breachwright/ROADMAP.md",
    "Breachwright/INSTALL.md",
    "Breachwright/INSTALL_WSL.md",
    "Breachwright/docs/DATA_SAFETY.md",
    "Breachwright/docs/RELEASE_NOTES_2.2.0.md",
    "Breachwright/SECURITY.md",
    "Breachwright/SUPPORT.md",
    "Breachwright/THIRD_PARTY_NOTICES.md",
    "Breachwright/TRADEMARKS.md",
    "Breachwright/VERSION",
}
FORBIDDEN_NAMES = {".env", ".secret_key", "breachwright.db"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_members(path: Path) -> set[str]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            return {
                PurePosixPath(info.filename.replace("\\", "/")).as_posix().rstrip("/")
                for info in archive.infolist()
                if not info.is_dir()
            }
    if path.name.lower().endswith((".tar.gz", ".tgz")):
        with tarfile.open(path, mode="r:gz") as archive:
            return {
                PurePosixPath(member.name.replace("\\", "/")).as_posix().rstrip("/")
                for member in archive.getmembers()
                if member.isfile() or member.issym() or member.islnk()
            }
    raise SystemExit(f"Unsupported archive type: {path}")


def select_archive(target: Path) -> Path:
    if target.is_file():
        return target
    if not target.is_dir():
        raise SystemExit(f"Archive path does not exist: {target}")
    candidates = sorted(
        path
        for path in target.glob("breachwright-*")
        if path.is_file()
        and (path.suffix.lower() == ".zip" or path.name.lower().endswith(".tar.gz"))
    )
    if len(candidates) != 1:
        raise SystemExit(
            f"Expected exactly one Breachwright archive in {target}; found {len(candidates)}"
        )
    return candidates[0]


def verify(path: Path) -> None:
    members = archive_members(path)
    if not members:
        raise SystemExit(f"Archive is empty: {path}")

    unsafe = sorted(
        name
        for name in members
        if PurePosixPath(name).is_absolute()
        or ".." in PurePosixPath(name).parts
        or PurePosixPath(name).parts[:1] != ("Breachwright",)
    )
    if unsafe:
        raise SystemExit(f"Archive contains unsafe or unexpected paths: {unsafe[:5]}")

    missing_documents = sorted(REQUIRED_DOCUMENTS - members)
    if missing_documents:
        raise SystemExit(f"Archive is missing required documents: {missing_documents}")

    dependency_licenses = {
        name
        for name in members
        if name.startswith("Breachwright/THIRD_PARTY_LICENSES/")
    }
    if len(dependency_licenses) < 10:
        raise SystemExit("Archive is missing the dependency license inventory")
    required_license_groups = {
        "Python FastAPI": "Breachwright/THIRD_PARTY_LICENSES/python/fastapi-",
        "JavaScript React": (
            "Breachwright/THIRD_PARTY_LICENSES/javascript/react-"
        ),
    }
    missing_license_groups = sorted(
        label
        for label, prefix in required_license_groups.items()
        if not any(name.startswith(prefix) for name in dependency_licenses)
    )
    if missing_license_groups:
        raise SystemExit(
            "Archive is missing required dependency licenses: "
            + ", ".join(missing_license_groups)
        )

    forbidden = sorted(
        name for name in members if PurePosixPath(name).name.lower() in FORBIDDEN_NAMES
    )
    if forbidden:
        raise SystemExit(f"Archive contains private runtime data: {forbidden}")

    windows = path.suffix.lower() == ".zip"
    required_launchers = (
        {"Breachwright/Breachwright.exe", "Breachwright/BreachwrightCLI.exe"}
        if windows
        else {"Breachwright/Breachwright", "Breachwright/BreachwrightCLI"}
    )
    missing_launchers = sorted(required_launchers - members)
    if missing_launchers:
        raise SystemExit(f"Archive is missing application launchers: {missing_launchers}")

    print(f"Verified archive: {path}")
    print(f"Files: {len(members)}")
    print(f"Bytes: {path.stat().st_size}")
    print(f"SHA-256: {sha256(path)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        type=Path,
        help="A release archive or a directory containing exactly one release archive.",
    )
    args = parser.parse_args()
    verify(select_archive(args.target.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
