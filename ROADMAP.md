# Breachwright roadmap

Breachwright is a community-focused, local-first penetration test management
project created by Advent Cybersecurity. This roadmap describes direction, not
promised dates. Issues and pull requests should preserve the product principles
in `CONTRIBUTING.md`.

## Release standards

Every supported binary release must:

- expose the same complete feature set on Windows and Linux
- preserve data created by the prior supported release
- keep AI optional for core engagement, evidence, reporting, export, and backup
  workflows
- pass source and packaged user journeys on Windows and Ubuntu
- pass native desktop, install, uninstall, and archive-integrity checks
- publish a checksum for every native archive
- exclude API keys, signing secrets, databases, logs, and assessment data
- use standard public GitHub-hosted runners and avoid paid test services

The project does not publish a new download when one supported platform is
failing its release gate.

## 2.1: portable and dependable

The 2.1 work focuses on making the complete application dependable for
long-running Windows and Linux installations:

- native Windows and Linux archives from one source tree
- verified backup and offline restore for SQLite installations
- deterministic Markdown and DOCX reports without an AI provider
- immediate access to a single local owner workspace without accounts or login
- bounded uploads, imports, job output, logs, and AI-generated records
- evidence-grounded AI proposals with explicit local review
- system diagnostics and explicit version reporting
- upgrade validation using data created by the public 2.0 release

## 2.2: repeatable assessments

The 2.2 foundation turns one-time testing records into a repeatable local
assessment workflow:

- immutable scan snapshots created from explicitly selected uploads
- deterministic new, persistent, resolved, and regressed classifications
- finding revision history, retest status, and retest due dates
- built-in assessment templates with automatic methodology checklists
- current OWASP Top 10:2025 web coverage and OWASP API Security Top 10:2023
  API coverage
- advisory report-readiness blockers and warnings
- Nuclei JSONL and SARIF 2.1 interchange
- portable project transfer for checklists, finding history, retest metadata,
  scan comparison history, reviewed AI provenance, and attack narratives
- deterministic risk-first reports with reviewed MITRE ATT&CK mappings

## 2.3: evidence workspace and asset coverage

The next product release should make the assessment workspace faster to use
during active testing:

- build an asset and service inventory from normalized scan observations
- link assets, services, findings, retests, and evidence without duplicating data
- add an evidence notebook for raw HTTP, HAR files, screenshots, and analyst notes
- provide local redaction controls before evidence is exported or sent to an AI
  provider
- add fast local search across scope, assets, findings, evidence, and checklists
- turn the retest queue into a due, overdue, and recently resolved work view
- allow safe, versioned export and import of user-created engagement and finding
  templates

## 2.4: community extensions and automation

The following release should make integrations dependable without creating a
hosted plugin service:

- publish a versioned parser contract and a fixture-based compatibility kit
- support declarative parser packs for common JSON, JSONL, XML, and CSV tools
- add contributor examples for a parser, report section, and methodology
- add a headless CLI for import, snapshot, readiness, report, export, and backup
  workflows
- add versioned machine-readable exports, including a documented OSCAL mapping
- evaluate an optional local HTTP workbench only after request storage,
  redaction, and certificate handling have passed the Windows and Linux gates

## Long-term quality and release trust

- expand sanitized fixtures for nmap, Nessus, Burp Suite, Nuclei, SARIF, and
  Active Directory variants
- grow the AI quality corpus with expected findings and deliberate non-findings
  without enabling paid CI calls
- add an append-only local audit log for evidence, reports, backups, restores,
  and Tool Runner actions
- show backup age and data-integrity status in diagnostics
- add optional release signing only after the project documents its signing
  identity and recovery process
- document a tested PostgreSQL backup and recovery procedure for Docker users

## Platform policy

Windows x64 and Linux x64 are the binary-release targets. Both must pass the
same application and data-compatibility journey, plus their native desktop and
installer checks.

macOS remains a source installation until the project has a repeatable native
build, desktop test, installation test, and signing approach that does not
weaken the release standards or introduce mandatory infrastructure cost.

## Cost and privacy guardrails

- Core workflows must not require an Advent-hosted service.
- Test automation must not call paid AI models.
- Model-provider configuration belongs to the operator.
- Local and self-hosted model endpoints remain first-class.
- Standard public GitHub runners are preferred for repeatable platform tests.
- Workflows must not retain candidate binaries before release approval.
- Adding a paid service or persistent cloud dependency requires an explicit
  public design decision and a free local alternative.

## How to propose work

Open a focused issue describing the user problem, affected workflow, platform,
data-compatibility impact, and proposed validation. Security vulnerabilities
must follow `SECURITY.md` instead of a public issue.
