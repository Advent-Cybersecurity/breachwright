"""Command-line backup and offline restore utility."""

import argparse
from pathlib import Path

from app.config import settings
from app.system.backup import create_backup, restore_backup, validate_backup
from app.version import APP_VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, validate, or restore a Breachwright backup."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="Create a local backup.")

    validate = commands.add_parser("validate", help="Validate a backup archive.")
    validate.add_argument("backup", type=Path)

    restore = commands.add_parser(
        "restore",
        help="Restore a backup while Breachwright is stopped.",
    )
    restore.add_argument("backup", type=Path)
    restore.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm that Breachwright is stopped and restore should proceed.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "create":
        path = create_backup(
            settings.data_dir,
            settings.resolved_database_url,
            APP_VERSION,
        )
        print(f"Backup created: {path}")
        return 0

    if args.command == "validate":
        manifest = validate_backup(args.backup)
        print(
            "Backup valid: "
            f"format {manifest['format_version']}, "
            f"app {manifest['app_version']}, "
            f"created {manifest['created_at']}"
        )
        return 0

    if not args.confirm:
        raise SystemExit(
            "Restore cancelled. Stop Breachwright, then run again with --confirm."
        )
    safety_path = restore_backup(
        args.backup,
        settings.data_dir,
        settings.resolved_database_url,
    )
    print(f"Restore complete. Previous data preserved at: {safety_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
