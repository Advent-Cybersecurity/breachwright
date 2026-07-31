# Data Safety

Breachwright stores assessment data locally by default. Back up that data
before upgrades, workstation changes, or major imports.

## What a backup contains

A Breachwright backup is a validated ZIP archive containing:

- A consistent SQLite database snapshot
- Finding evidence attachments
- Evidence Notebook attachments
- Uploaded scan files
- Generated reports
- Custom report-template assets
- Tool Runner output files
- A manifest with file sizes and SHA-256 checksums

The archive does not contain `.env` or a legacy `.secret_key` file. This
prevents configured API keys or authentication material left by an older
installation from entering a portable archive. Store provider configuration
separately if you need to reproduce it.

Built-in backup and restore currently support the default SQLite deployment.
PostgreSQL deployments should use PostgreSQL-native backup tools.

## Check local data integrity

Open **Settings** and review both diagnostic results:

- **Database integrity** runs SQLite's built-in quick check.
- **Stored file integrity** verifies that database-backed scan, finding
  evidence, Evidence Notebook, and report files still exist on disk.

The stored-file check is bounded to 10,000 records and clearly labels a partial
result. Use **Refresh** after repairing or restoring files. A healthy database
does not prove that files moved or deleted outside Breachwright are present,
which is why the two checks are reported separately.

Settings also reports whether no verified backup exists and whether the newest
backup is current, aging, or stale. Create a new backup after confirming both
integrity checks.

## Create and download a backup

Open **Settings**, select **Create Backup**, and download the resulting ZIP
file.

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

Packaged Windows users can run:

```powershell
.\BreachwrightCLI.exe --validate-backup C:\path\to\breachwright-backup.zip
```

Packaged Linux users can run:

```bash
./BreachwrightCLI --validate-backup /path/to/breachwright-backup.zip
```

Source installations can run:

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
finding evidence, notebook attachments, uploads, reports, custom template
assets, and Tool Runner output are moved into a timestamped
`restore-safety-*` folder. Keep that folder until you confirm the restored
installation works.
