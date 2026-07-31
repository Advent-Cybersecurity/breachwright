# Changelog

## v2.1.0 (unreleased)

### Reliability and data safety

- Added verified local SQLite backups for the database, evidence, uploads, and reports
- Added offline restore with archive checksums, SQLite integrity checks, rollback, and preservation of displaced data
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
- Added self-service password changes with current-password verification and
  immediate revocation of existing account sessions
- Made AI report enhancement an explicit opt-in
- Added semantic version precedence so older releases are not presented as updates
- Added accessible labels to first-run, login, engagement, and finding forms
- Added accessible names to assistant message and send controls
- Added dialog semantics, named close controls, Escape-key support, and accessible account fields
- Added release-candidate version visibility across the API, desktop launcher, and frontend
- Split large frontend pages into on-demand bundles to reduce the initial JavaScript download
- Moved dashboard finding counts into database aggregation so large projects do not load every finding into memory
- Added interface error recovery and predictable unknown-route handling
- Fixed first-run validation failures so they show readable feedback instead of crashing the interface
- Fixed login failures so the server's useful authentication message is shown
  instead of a generic unauthorized error
- Fixed session restoration after desktop WebView and browser page reloads

### Security

- Added password length, email, duplicate-user, CVSS, date, and import validation
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
