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

## Next priorities

### 1. Release trust and recovery

- add optional release signing when the project has a documented signing
  identity and recovery process
- add a guided restore workflow that still requires the application to be
  offline before replacement
- show backup age and data-integrity status in diagnostics
- document a tested PostgreSQL backup and recovery procedure for Docker users

### 2. Repeatable assessment workflows

- introduce reusable engagement templates for scope, methodology, report
  template, and required evidence
- add safe finding-template import and export with explicit schema versions
- add clearer retest queues, due dates, and remediation status history
- make report validation identify incomplete evidence and unresolved retests
  before generation

### 3. Better local analysis

- expand sanitized parser fixtures for more nmap, Nessus, Burp Suite, nuclei,
  and Active Directory variants
- grow the quality corpus with community-contributed expected findings and
  deliberate non-findings
- add optional local-model comparison reports without enabling paid CI calls
- improve evidence retrieval for very large assessments while preserving
  explicit context limits

### 4. Community extension points

- define a documented parser interface with fixture-based compatibility tests
- define versioned import and export schemas
- add contributor examples for a parser, report section, and methodology
- publish a compatibility policy before accepting third-party extensions

### 5. Local accountability

- add an append-only audit log for finding, evidence, report, backup,
  restore, and Tool Runner actions
- add review history for manual and AI-assisted finding changes
- keep the default product focused on one local operator and avoid hidden
  network-service assumptions

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
