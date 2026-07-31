# Changelog

## Unreleased

### Active assessment workspace

- Added an engagement Overview with current finding, asset, retest,
  methodology, scan-snapshot, notebook, readiness, and recent local activity
  summaries.
- The Overview can be refreshed during long assessments and preserves healthy
  sections when one local data source is temporarily unavailable.
- Engagements now open on the Overview, and Ctrl+K or Command+K focuses the
  local workspace search from any engagement tab.
- Added a latest-snapshot asset and service inventory with aliases, operating
  system details, linked findings, evidence, retests, and deterministic change
  states.
- Added fast local engagement search across findings, checklist items, assets,
  finding evidence metadata, notebook notes and attachments, and exploitation
  chains.
- Added an Evidence Notebook for bounded analyst notes, asset references, tags,
  and validated attachments. Reviewed notes can become non-AI findings while
  retaining immutable note and attachment provenance.
- Added due, overdue, scheduled, and recently remediated retest work views,
  finding and retest filters, and risk-first deterministic ordering.
- Scanner observations can be explicitly reviewed into findings without an AI
  provider. Duplicate promotion is prevented and provenance is retained.
- Manual finding entry now warns about exact-title duplicates and highlights
  overlapping affected hosts without blocking legitimate separate records.

### Reuse, interoperability, and privacy

- Added local CRUD plus strict versioned import and export for user-created
  assessment templates and finding templates. Finding templates exclude
  target-specific hosts and evidence.
- Expanded evidence validation to HTTP, request, response, HAR, text,
  Markdown, CSV, and JSON files in addition to supported images and PDF.
- Added spreadsheet-safe findings CSV export with local secret redaction on by
  default, plus optional redaction for SARIF output.
- Added a visible local secret-redaction control for scanner analysis,
  assistant questions, and other AI context, plus complete Settings forms for
  Anthropic, OpenAI, Azure OpenAI, AWS Bedrock, and local OpenAI-compatible
  providers.
- Completed Nmap and Nuclei Tool Runner output can be added directly to Scans.
  Any finished Tool Runner output can be preserved in the Evidence Notebook,
  and captured structured artifacts remain bounded.
- Verified backups now include Evidence Notebook attachments.

### Reliability and validation

- Fixed finding-list ordering so client-side filters do not disturb the
  backend's deterministic risk-first order.
- Asset inventory summary counts remain complete while host, observation, and
  linked-finding details are explicitly bounded for interface responsiveness.
- Settings now shows whether no verified backup exists, whether the newest
  backup is aging, or whether a verified backup was created today.
- System diagnostics now checks up to 10,000 database-backed scan, evidence,
  notebook, and report files and distinguishes missing files from database
  integrity failures. Users can rerun the check from Settings after repairs.
- AI scanner analysis now rejects more than 50 files or 250 MB of combined
  input before provider initialization and uses bounded reads for every file.
- AI scanner analysis now includes a provider-free input preflight showing
  file count, combined size, active provider, local redaction state, and
  actionable readiness issues.
- Users can explicitly choose the uploaded scans included in each AI analysis,
  keeping unrelated evidence intact while controlling disclosure and provider
  usage.
- Scan management now shows stored size and Tool Runner origin, includes quick
  AI and snapshot selection controls, and prevents either selection from
  exceeding its 50-file processing limit.
- Added migration, API, backup and restore, bounded-output, redaction,
  provenance, duplicate-prevention, and complete local user-journey coverage
  for the new workflows.
- Packaged Windows and Linux user journeys now cover scan metadata, provider-free
  AI preflight, recent workspace activity, Tool Runner reuse, reports, backup,
  and restore in addition to core assessment workflows.

## v2.2.0 (2026-07-31)

### Repeatable assessment workflows

- Added versioned scan snapshots with deterministic new, persistent, resolved,
  and regressed classifications.
- Large comparisons retain complete counts while bounding rendered detail rows
  per status to keep the local interface responsive.
- Added finding change history, retest due dates, and an engagement retest queue.
- Finding and retest views now use risk-first ordering with deterministic ties.
- Added built-in web, API, network, Active Directory, and cloud engagement
  templates.
- Updated web templates to the current OWASP Top 10:2025 categories, including
  Software Supply Chain Failures and Mishandling of Exceptional Conditions.
- API engagements now receive a dedicated OWASP API Security Top 10 (2023)
  checklist instead of the general web checklist.
- Added report readiness checks with actionable blockers and warnings.
- Report readiness now warns when uploaded scans are not represented in any
  versioned snapshot.
- Added Nuclei JSONL and SARIF 2.1 import support, plus SARIF finding export.
- Engagement exports now use format 1.1 and preserve status, template,
  checklist progress, finding change history, normalized scan snapshot
  history, AI review provenance, CVSS zero scores, and retest scheduling
  metadata. Generated attack narratives and MITRE technique mappings also
  round-trip without requiring an AI provider, including the saved
  engagement-wide narrative. Finding references inside imported exploitation
  chains and saved narrative citations are remapped to the new local finding
  IDs.

### Reporting, installation, and release quality

- Reports now use deterministic risk-first finding and attack-path ordering.
- Finding views, learned defaults, narrative context, and DOCX reports preserve
  valid CVSS zero scores. DOCX output no longer duplicates attack paths already
  present in the shared report content or summary sections already represented
  by the native Word layout.
- Generated reports record the selected template name, and invalid template
  selections return a clear error instead of silently changing branding.
- If Word generation falls back to Markdown, the saved report and interface
  now show the actual format and do not claim that DOCX branding was applied.
- A shared AI context ceiling prevents oversized reports, attack paths,
  narratives, methodology reviews, and Active Directory datasets from creating
  an accidental large or expensive provider request. Local workflows remain
  available without that provider limit.
- Reviewed attack-path narratives and MITRE ATT&CK mappings are included in
  deterministic Markdown and DOCX reports without an AI provider.
- Updated the WSL guide for the current Linux archive, direct local workspace,
  data location, browser mode, and optional AI setup.
- Added the WSL guide and 2.2 release notes to each native release archive and
  made archive validation require them.
- Added regression coverage that prevents obsolete account-setup commands from
  returning to Windows, Linux, or WSL installation instructions.
- Installer banners and shortcuts identify Breachwright as open source and
  created by Advent Cybersecurity without presenting AI as a requirement.
- Replaced silent report, evidence, finding-history, checklist, Active
  Directory, Tool Runner, and Settings load failures with actionable interface
  errors.

## v2.1.0 (unreleased foundation)

### Reliability and data safety

- Added verified local SQLite backups for the database and user-managed files
- Portable backups include custom template assets and Tool Runner output
- Added offline restore with archive checksums, SQLite integrity checks, rollback, and preservation of displaced data
- Backup validation now rejects unsigned databases and unmanifested archive files
- Restore validation rejects cross-platform path aliases and Windows alternate streams
- Added authenticated system diagnostics and backup management in Settings
- Added confirmed backup deletion so long-running installations can manage disk usage
- Fixed startup so migration failures and timeouts stop the application instead of reporting false success
- Added cleanup for evidence records and files when findings or engagements are deleted
- Fixed bulk finding deletion so evidence files are removed with their records
- Restricted direct finding updates to supported retest states
- Bounded live Tool Runner output to 500 KB per job while retaining the newest
  output and marking truncation
- Added bounded log rotation to prevent unattended installations from growing
  the application log indefinitely

### Reporting and usability

- Added complete Markdown and DOCX reporting without an AI provider
- Added administrator account listing, role changes, deactivation, and reactivation
- Account deactivation and reactivation now revoke all prior sessions
- Added self-service password changes with current-password verification and
  immediate revocation of existing account sessions
- Made AI report enhancement an explicit opt-in
- Included the AWS SDK so the advertised Bedrock provider works in source and packaged installs
- Added a no-request CLI provider diagnostic and packaged Bedrock smoke test
- Added semantic version precedence so older releases are not presented as updates
- Added accessible labels to first-run, login, engagement, and finding forms
- Added accessible names to assistant message and send controls
- Added dialog semantics, named close controls, Escape-key support, and accessible account fields
- Added release-candidate version visibility across the API, desktop launcher, and frontend
- Split large frontend pages into on-demand bundles to reduce the initial JavaScript download
- Moved dashboard finding counts into database aggregation so large projects do not load every finding into memory
- Added interface error recovery and predictable unknown-route handling
- Fixed unknown API routes returning an empty successful response
- Fixed first-run validation failures so they show readable feedback instead of crashing the interface
- Unified graphical, command-line, and browser first-run account validation
- Fixed login failures so the server's useful authentication message is shown
  instead of a generic unauthorized error
- Fixed session restoration after desktop WebView and browser page reloads
- Fixed engagement deletion so methodology checklist data is removed reliably
- Fixed Docker Compose persistence for evidence, configuration, and signing data
- Bounded upload reads before validating scan, evidence, logo, and Active Directory file sizes
- Bounded assistant messages and bulk finding selections before processing
- Added bounded schema validation for AI-generated findings, attack paths,
  Active Directory paths, and gap-analysis results before they reach
  engagement data or the interface

### Security

- Added password length, email, duplicate-user, CVSS, date, and import validation
- Added bounded login-failure throttling and equalized password verification
  for unknown accounts
- Serialized first-run administrator creation so concurrent setup requests
  cannot both initialize the application
- Added bounded attack-path validation and rollback coverage for engagement imports
- Prevented scan filename and frontend fallback path traversal
- Added scan and import size limits
- Removed SVG report-template uploads and added PNG and JPEG signature checks
- Added PNG, JPEG, GIF, WebP, and PDF signature checks for evidence uploads
- Added SharpHound ZIP entry, expansion, member-size, and compression-ratio limits
- Prevented environment-file line injection and made provider updates atomic
- Added browser security headers and disabled API response caching
- Removed raw HTML rendering from assistant messages so user and model content
  is always escaped by React
- Made viewer accounts read-only across engagement data, reports, uploads, Tool Runner, and AI-assisted actions
- Fixed Windows backup staging permissions in the packaged runtime
- Added an on-demand SQLite integrity check to system diagnostics

### Testing and packaging

- Added a real first-run user journey against Uvicorn and SQLite
- Added Windows and Linux CI coverage on standard public GitHub runners
- Replaced the broken legacy builder with one cross-platform candidate pipeline
- Added packaged API, frontend, report, backup, restore, and desktop-window smoke tests
- Added a real v2.0.0 database upgrade smoke test
- Added separate native Windows and Linux archives built from the same source
- Added a release-bundled installation guide covering checksums, first run,
  data locations, backup, and uninstall behavior
- Made Linux installation honor `XDG_DATA_HOME`
- Added release-archive verification for required notices, launchers, checksums, and private-data exclusions
- Fixed Linux bundle installation, legacy data migration, uninstall cleanup, and data preservation
- Added a packaged CLI version command and Linux install/uninstall smoke test
- Added non-interactive Windows bundle install/uninstall validation with data-preservation checks
- Made the Windows installer lifecycle test runnable and self-cleaning outside
  GitHub Actions
- Isolated and cleaned logging-test data so validation runs leave no test
  secret or runtime directory in the source tree
- Added a public roadmap with cross-platform release, privacy, compatibility,
  community-extension, and $0 automation guardrails
- Removed dependency test and type-checker modules from release bundles
- Removed internal runtime-path debug output from packaged command-line operations
- Aligned packaged and source data-directory selection on Windows and Linux
- Added a machine-readable version file to every native release archive

## v2.0.0

### Open-source release

- Released the complete application under Apache License 2.0
- Added Advent Cybersecurity origin attribution in `README.md` and `NOTICE`
- Removed activation keys, signed entitlement tokens, subscription checks, and the remote activation server dependency
- Removed all feature, engagement, finding, and seat limits
- Removed upgrade prompts and edition-specific interface elements
- Made exploitation chains, attack narratives, Active Directory analysis, Tool Runner, evidence, export/import, custom prompts, report templates, local models, cross-engagement intelligence, and methodology gap analysis available to every installation
- Removed the legacy hosted AI provider because it depended on Advent-operated infrastructure and private service authentication
- Kept AI workflows available through Anthropic, OpenAI, Azure OpenAI, AWS Bedrock, and local or self-hosted endpoints
- Added security, contribution, support, conduct, trademark, architecture, CI, and dependency-update files

## v1.7.2 (2026-03-22)

### Packaging and branding

- Added application icons for Windows and Linux
- Forced the EdgeChromium backend on Windows
- Bundled icons in packaged builds
- Standardized the canonical environment-file location

## v1.7.1 (2026-03-21)

### Windows support

- Added cross-platform PyInstaller builds
- Added Windows installer, uninstaller, and build scripts
- Added a graphical first-run setup flow
- Improved Windows console and download compatibility

### In-app setup

- Added first-run setup in the application
- Added setup and setup-status API endpoints
- Kept the command-line setup path for Linux users

## v1.7.0 (2026-03-17)

### Product packaging

- Simplified the former commercial packaging model
- Expanded the free feature set
- Improved Active Directory analysis response parsing

## v1.6.0 (2026-03-16)

### AI and infrastructure

- Added a legacy hosted offensive-security AI provider
- Added local AI assistant access through user-supplied provider keys
- Added licensing, subscription-management, and offline-token infrastructure
- Fixed environment-file persistence and WebKit caching

## v1.5.0 (2026-03-10)

### Distribution

- Added remote activation, signed tokens, offline validation, and seat management
- Added AWS-based distribution and account infrastructure

These mechanisms were removed in v2.0.0.

## v1.2.0 (2026-03-06)

### Advanced workflows

- Added cross-engagement intelligence
- Added methodology gap detection
- Added multi-tool output correlation
- Added local-model support
- Improved job persistence, file logging, secret-key generation, and AI response parsing

## v1.0.0 (2026-03-05)

### Core

- Engagement and finding management
- User authentication and role-based access
- SQLite with Alembic migrations
- Desktop application through pywebview
- Light and dark themes

### Analysis and reporting

- nmap, Nessus, and Burp Suite ingestion
- AI-assisted findings and exploitation chains
- Custom AI prompts
- Anthropic, OpenAI, Azure OpenAI, and AWS Bedrock integrations
- SharpHound and BloodHound ZIP import
- Active Directory attack-path analysis
- Markdown and DOCX reports
- Evidence attachments and severity charts

### Operator workflows

- Background Tool Runner jobs
- Tool availability detection
- Context-aware AI assistant
- Engagement export and import
- AI-provider configuration
