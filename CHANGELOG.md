# Changelog

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
