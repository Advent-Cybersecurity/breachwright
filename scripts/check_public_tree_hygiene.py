#!/usr/bin/env python3
"""Reject local Codex state and recognizable chat exports from Git tracking.

The export filename rule is deliberately narrow. It requires a ``codex`` or
``chatgpt`` prefix, a ``chat``, ``session``, ``thread``, or ``conversation``
kind, an explicit ``export`` token, and a common text/archive extension. This
avoids rejecting ordinary product files such as ``session.json``.

The guard scans only the Git index. Diagnostics contain tracked paths and
marker labels, never matched content or ignored local files.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys


RESERVED_BASENAMES = frozenset({"codex_session.md", "agents.md"})
EXPORT_BASENAME = re.compile(
    r"^(?:codex|chatgpt)[._-](?:chat|session|thread|conversation)"
    r"[._-]export(?:[._-][a-z0-9][a-z0-9._-]*)?"
    r"\.(?:json|jsonl|md|txt|html|zip)$",
    re.IGNORECASE,
)

# Construct these values so the guard does not contain and flag its own
# recognizable export markers.
CONTENT_MARKERS = (
    ("thread identifier", ("source" + "_thread_id").encode("ascii")),
    ("delegation tag", ("<codex" + "_delegation>").encode("ascii")),
    (
        "cross-thread send call",
        ("codex_app." + "send_message" + "_to_thread").encode("ascii"),
    ),
)


def run_git(*args: str, allow_no_match: bool = False) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode == 0:
        return completed.stdout
    if allow_no_match and completed.returncode == 1:
        return b""
    detail = completed.stderr.decode("utf-8", errors="replace").strip()
    raise RuntimeError(f"git command failed: {detail}")


def tracked_paths() -> list[str]:
    output = run_git("ls-files", "-z")
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in output.split(b"\0")
        if item
    ]


def forbidden_path_reason(path: str) -> str | None:
    parts = path.replace("\\", "/").split("/")
    folded = [part.casefold() for part in parts]
    if folded[-1] in RESERVED_BASENAMES:
        return "reserved local instruction/session basename"
    if ".codex" in folded:
        return "local .codex path"
    if EXPORT_BASENAME.fullmatch(parts[-1]):
        return "recognizable Codex/ChatGPT chat or session export filename"
    return None


def paths_containing(marker: bytes) -> list[str]:
    output = run_git(
        "grep",
        "--cached",
        "-l",
        "-z",
        "-F",
        "-e",
        marker.decode("ascii"),
        "--",
        allow_no_match=True,
    )
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in output.split(b"\0")
        if item
    ]


def run_self_test() -> None:
    cases = {
        "AGENTS.md": True,
        "nested/agents.MD": True,
        "nested/CODEX_SESSION.md": True,
        "source/.CoDeX/settings.json": True,
        "codex-chat-export.json": True,
        "exports/ChatGPT_conversation_export-2026-11-27.md": True,
        "session.json": False,
        "docs/product-chat-exporter.md": False,
        "scripts/check_public_tree_hygiene.py": False,
    }
    for path, expected in cases.items():
        if (forbidden_path_reason(path) is not None) != expected:
            raise AssertionError(f"path self-test failed for {path!r}")

    with open(__file__, "rb") as guard_file:
        source = guard_file.read()
    if any(marker in source for _, marker in CONTENT_MARKERS):
        raise AssertionError("guard source contains a complete protected marker")


def audit() -> int:
    paths = tracked_paths()
    path_findings = [
        (path, reason)
        for path in paths
        if (reason := forbidden_path_reason(path)) is not None
    ]
    content_findings = sorted(
        (path, label)
        for label, marker in CONTENT_MARKERS
        for path in paths_containing(marker)
    )

    if not path_findings and not content_findings:
        print(
            "Public-tree hygiene check passed: "
            f"{len(paths)} tracked paths, 0 forbidden paths, "
            "0 recognizable chat/session marker locations."
        )
        return 0

    print(
        "Public-tree hygiene check failed: "
        f"{len(path_findings)} forbidden tracked path(s), "
        f"{len(content_findings)} recognizable marker location(s).",
        file=sys.stderr,
    )
    for path, reason in sorted(path_findings):
        print(f"  {path} [{reason}]", file=sys.stderr)
    for path, label in content_findings:
        print(f"  {path} [{label}]", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("Public-tree hygiene guard self-test passed.")
        return 0
    return audit()


if __name__ == "__main__":
    raise SystemExit(main())
