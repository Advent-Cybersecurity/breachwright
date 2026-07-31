# Breachwright 2.2.0

Breachwright 2.2 turns the local assessment workspace into a repeatable retest
workflow. Advent Cybersecurity created Breachwright and provides the official
repository as a fully open-source project. The Windows and Linux packages
contain the same complete feature set, with no accounts, activation, paid
tiers, seat limits, or feature gates.

## Repeatable assessments

- Create immutable snapshots from explicitly selected Nmap, Nessus, Burp
  Suite, Nuclei JSONL, or SARIF uploads.
- Compare each snapshot with its prior baseline as new, persistent, resolved,
  or regressed observations.
- Keep an immutable history of finding changes and schedule findings for
  retest.
- Start web, API, network, Active Directory, or cloud assessments from built-in
  templates with automatic methodology checklists.
- Use the current OWASP Top 10:2025 categories for web assessments.
- Review report-readiness blockers and warnings before creating a deliverable.
- Use a dedicated OWASP API Security Top 10 (2023) checklist for API work.

The OWASP Top 10 checklists are baselines and do not represent complete
penetration-test coverage. Use the verification standard and methodology that
fit the assessment scope.

## Project portability

Engagement JSON format 1.1 carries editable project records between
installations. It preserves engagement state, checklist progress, findings,
finding history, retest metadata, normalized snapshot history, reviewed AI
provenance, attack paths, MITRE ATT&CK mappings, and saved narrative content.
References to findings are remapped to the newly imported local records.

Portable JSON is intentionally not a full backup. Raw scan files, binary
evidence, Active Directory datasets, pending AI proposals, generated reports,
and Tool Runner output remain in the verified full-workspace backup.

## Reporting

- Markdown and DOCX reports remain available without an AI provider.
- Findings and attack paths use deterministic risk-first ordering.
- Valid CVSS zero scores remain visible in Word reports.
- Reviewed attack narratives and MITRE ATT&CK mappings appear once in each
  report.
- Optional AI report enhancement remains an explicit user choice and is
  checked for required findings and evidence references.
- Oversized report, attack-path, narrative, methodology, and Active Directory
  AI context is rejected before any provider request, while local workflows
  remain available.

## Safety and compatibility

- Malformed, unsupported, or oversized project imports fail without leaving a
  partial imported engagement.
- Parser values, nested SARIF data, comparison details, uploads, and generated
  records are bounded.
- Mixed or outdated snapshot parser versions produce visible advisory warnings.
- A copied Breachwright 2.0 database is upgraded and tested as part of each
  Windows and Linux candidate build.
- Windows and Linux archives must pass source, packaged, desktop, installer,
  backup, restore, data-preservation, and archive-integrity checks before a
  release is published.

## Downloads

The planned native archives are:

- `breachwright-2.2.0-windows-x64.zip`
- `breachwright-2.2.0-linux-x64.tar.gz`

Verify each published SHA-256 checksum before installing. macOS remains a
source installation because it does not yet have the same repeatable native
build and desktop test gate.

## Cost and privacy

Core workflows are local and require no Advent-hosted infrastructure. Release
tests use standard GitHub-hosted runners, retain no candidate artifacts, and do
not call paid AI models. Optional external AI providers can charge for user
initiated requests. Local compatible model servers remain supported.

Back up the workspace from **Settings > Data Safety** before upgrading. Read
`INSTALL.md` and `docs/DATA_SAFETY.md` for platform paths and offline restore
instructions.
