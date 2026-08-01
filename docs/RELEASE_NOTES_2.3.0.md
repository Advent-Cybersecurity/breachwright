# Breachwright 2.3.0

Breachwright 2.3 expands the local workspace for active penetration testing.
Advent Cybersecurity created Breachwright and releases the complete application
as open-source software for the security community. Windows and Linux packages
contain the same feature set, with no accounts, activation, paid editions, seat
limits, or feature gates.

## Active assessment workspace

- A refreshable engagement Overview brings together findings, asset coverage,
  retest priorities, methodology progress, evidence, readiness, and recent
  local activity.
- Local search spans findings, checklist items, assets, evidence metadata,
  notebook notes, attachments, and exploitation chains.
- Scan snapshots now provide an asset and service inventory with aliases,
  operating-system details, linked evidence, and deterministic new,
  persistent, resolved, and regressed states.
- Retest views distinguish overdue, scheduled, recently remediated, and due
  work without changing deterministic risk-first ordering.

## Evidence, scanners, and reusable work

- The Evidence Notebook preserves bounded analyst notes and validated
  attachments before they are ready to become findings.
- Scanner observations and reviewed notebook notes can become findings without
  an AI provider while retaining provenance.
- Nmap and Nuclei Tool Runner results can be copied into Scans, and finished
  tool output can be preserved in the Evidence Notebook.
- Scan upload supports conservative local detection for Nmap, Nessus, Burp
  Suite, Nuclei JSONL, and SARIF, with raw fallback and manual override.
- User-created assessment and finding templates support strict versioned local
  import and export.
- Findings CSV output is spreadsheet-safe and redacted by default. SARIF can
  also be redacted before export.

## AI privacy and reliability

- AI actions show the selected provider, local redaction state, input size,
  readiness, and potential external-provider cost before use.
- Scanner, Assistant, report, coverage, narrative, exploitation-chain, Active
  Directory, and Tool Runner context is explicitly bounded before provider
  initialization.
- Assistant answers retain only citations present in the final bounded prompt.
- Provider failures return a safe local message without copying raw provider
  response text into the interface or logs.
- Core findings, evidence, reporting, export, backup, and scanner-correlation
  workflows remain available without an AI provider.

## Safety and operations

- Verified backups include Evidence Notebook attachments and can be validated
  from the packaged CLI without changing local data.
- Settings keeps damaged backups visible, reports stored-file integrity and
  backup freshness, and can download a privacy-bounded support snapshot.
- Stored report, attachment, and scan deletion preserves the database record
  when the underlying file cannot be removed, allowing a retry.
- Tool Runner presets are reconstructed from validated server inputs and reject
  shell-control injection. Custom mode launches only the selected supported
  tool directly, without a command shell, and requires confirmation.
- App-owned file paths canonicalize record UUIDs and remain contained beneath
  the configured data directory. Operational logs omit user-controlled paths
  and labels.
- Packaged Tool Runner processes start independently from Breachwright's
  PyInstaller runtime so third-party scanner startup remains isolated.
- Credential redaction handles headers and private-key blocks without
  backtracking-prone searches over assessment data.
- Active Directory imports use bounded ZIP reads, deterministic dataset
  selection, indexed relationship summaries, and explicit cascade-deletion
  confirmation.
- The local API accepts only loopback Host headers. The launcher reports an
  occupied or invalid port immediately instead of opening another local
  service.
- Source builds require Node.js 20 or newer, and the Linux source installer
  uses the committed npm lockfile.

## Downloads

- `breachwright-2.3.0-windows-x64.zip`
- `breachwright-2.3.0-linux-x64.tar.gz`
- `SHA256SUMS.txt`

Verify the published SHA-256 checksum before installation. macOS remains a
source installation until it has the same repeatable native build, desktop,
installation, and signing gates.

The Windows executables are not currently Authenticode-signed. Windows may
show an unknown-publisher or Microsoft Defender SmartScreen warning. Download
only from the official Advent Cybersecurity GitHub release and do not run the
files if their SHA-256 values differ from `SHA256SUMS.txt`.

Back up the workspace from **Settings > Data Safety** before upgrading. Read
`INSTALL.md`, `docs/DATA_SAFETY.md`, and `SECURITY.md` for platform paths,
restore procedures, and the single-owner local security model.
