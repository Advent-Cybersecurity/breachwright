# Breachwright 2.1.0

Breachwright 2.1 is the first cross-platform binary release prepared after
Advent Cybersecurity made the complete product open source. Every application
feature is available without activation, paid product tiers, seat limits, or
usage limits.

## Highlights

- Windows x64 and Linux x64 packages built from the same source and data model
- Native installation and uninstall scripts that preserve application data
- Complete Markdown and DOCX report generation without an AI provider
- Administrator account management and read-only viewer roles
- Self-service password changes and reliable session revocation
- Verified SQLite backups with offline restore, rollback, and secret exclusion
- Backup coverage for evidence, scans, reports, template assets, and Tool
  Runner output
- System diagnostics, version visibility, and bounded application logs
- Safer evidence, scan, logo, Active Directory, and engagement-import handling
- Validation and size limits for AI-generated findings and attack paths
- Bounded Tool Runner output and cleanup of deleted engagement data
- Browser interface accessibility and error-recovery improvements
- Anthropic, OpenAI, Azure OpenAI, AWS Bedrock, and local compatible model
  support

## Downloads

The release is prepared as two native archives:

- `breachwright-2.1.0-windows-x64.zip`
- `breachwright-2.1.0-linux-x64.tar.gz`

The archives contain the desktop application, command-line executable,
installation guide, license, notices, security policy, and data-safety guide.
Review the published SHA-256 checksum before installation.

There is no macOS binary archive in this release. macOS users can run
Breachwright from source.

## Upgrading from 2.0

Back up the current Breachwright data directory before upgrading. The 2.1
candidate workflow opens a copied 2.0 database, runs every migration, and
verifies that the account, engagement, and finding remain intact.

Uninstalling a packaged application preserves its data by default. See
`INSTALL.md` and `docs/DATA_SAFETY.md` before replacing application files or
restoring a backup.

## AI providers and cost

AI configuration is optional. Manual findings, evidence management,
checklists, deterministic reports, export/import, diagnostics, and backups
work without an AI provider.

Third-party model services, including AWS Bedrock, may charge for requests.
Breachwright does not make a model request during installation or release
testing. The command-line `--provider-status` check validates configuration
without sending a model request.

## Deployment notes

Built-in portable backup and restore currently support SQLite installations.
Docker Compose uses PostgreSQL, so Docker operators must back up both the
PostgreSQL volume and the persisted `./data` directory.

Breachwright processes sensitive assessment data and can execute
operator-supplied security-tool commands. Keep it on a trusted host, use only
authorized targets, restrict editing accounts, and do not expose the API
directly to an untrusted network.

## Release validation

The release gate requires all of the following before publication:

- Source tests and dependency audits on Windows and Ubuntu
- CodeQL analysis
- Clean Windows and Linux package builds
- Packaged first-run and offline user journeys
- Native desktop-window checks
- Install, version, uninstall, and data-preservation checks
- Upgrade from a copied 2.0 database
- Release archive content and checksum inspection

The existing public 2.0 release remains unchanged until the 2.1 archives and
checksums receive deliberate final approval.
