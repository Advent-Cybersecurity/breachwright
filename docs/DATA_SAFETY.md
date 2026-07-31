# Data Safety

Breachwright stores assessment data locally by default. Back up that data
before upgrades, workstation changes, or major imports.

## What a backup contains

A Breachwright backup is a validated ZIP archive containing:

- A consistent SQLite database snapshot
- Evidence attachments
- Uploaded scan files
- Generated reports
- Custom report-template assets
- Tool Runner output files
- A manifest with file sizes and SHA-256 checksums

The archive does not contain `.env` or `.secret_key`. This prevents configured
API keys and the local token-signing secret from being copied into a portable
archive. Store those separately if you need to reproduce the same
configuration.

Built-in backup and restore currently support the default SQLite deployment.
PostgreSQL deployments should use PostgreSQL-native backup tools.

## Create and download a backup

Administrators can open **Settings**, select **Create Backup**, and download
the resulting ZIP file.

Packaged installations also include a command-line companion:

### Windows

```powershell
.\BreachwrightCLI.exe --create-backup
```

### Linux

```bash
./BreachwrightCLI --create-backup
```

Source installations can use:

```bash
python -m app.system.backup_cli create
```

Run the source command from the `backend` directory or set `PYTHONPATH` to
that directory.

## Validate a backup

```bash
python -m app.system.backup_cli validate /path/to/breachwright-backup.zip
```

Validation checks the archive layout, manifest version, file sizes, and every
SHA-256 checksum.

## Restore a backup

Stop Breachwright before restoring. Restoring while the application is
running is intentionally unsupported.

### Windows

```powershell
.\BreachwrightCLI.exe --restore-backup C:\path\to\breachwright-backup.zip --confirm-restore
```

### Linux

```bash
./BreachwrightCLI --restore-backup /path/to/breachwright-backup.zip --confirm-restore
```

### Source installation

```bash
python -m app.system.backup_cli restore /path/to/breachwright-backup.zip --confirm
```

Before replacing the database or data folders, Breachwright validates the
entire archive and runs SQLite integrity checks. The displaced database,
evidence, uploads, reports, custom template assets, and Tool Runner output are
moved into a timestamped
`restore-safety-*` folder. Keep that folder until you confirm the restored
installation works.
