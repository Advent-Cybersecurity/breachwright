# Breachwright architecture

## Product boundary

Breachwright is a local-first penetration test management application. It combines a FastAPI backend, a React interface, and an optional desktop window. The same backend can use SQLite for a single-host installation or PostgreSQL in the Docker deployment.

All application capabilities are part of the open-source distribution. There is no activation, entitlement, seat, engagement, or finding-limit service.

## Major components

| Area | Location | Responsibility |
| --- | --- | --- |
| API composition | `backend/app/main.py` | Starts the service, runs migrations, registers routers, exposes health and update checks, and serves the built frontend |
| Authentication | `backend/app/auth` | First-run administrator setup, JWT sessions, roles, and user management |
| Engagement data | `backend/app/engagements` | Engagements, findings, attack paths, reports, scans, settings, export, and import |
| Scan analysis | `backend/app/analysis` | Uploads scan data, parses supported formats, calls the configured AI provider, deduplicates findings, and updates knowledge data |
| Correlation | `backend/app/correlation` | Normalizes structured output from several tools and correlates hosts and findings |
| Active Directory | `backend/app/ad` | Parses SharpHound and BloodHound ZIP exports and creates attack-path data |
| Attack paths | `backend/app/attack_paths` | Generates exploitation chains from engagement findings |
| Narratives | `backend/app/narrative` | Produces path-level and engagement-level assessment narratives |
| Reports | `backend/app/reports` | Generates Markdown and DOCX reports and manages custom templates |
| Evidence | `backend/app/findings/evidence.py` | Stores and serves attachments associated with findings |
| Tool Runner | `backend/app/jobs` | Launches operator-supplied local commands, captures output, tracks status, and persists job records |
| Methodologies | `backend/app/checklists` and `backend/app/gap_detection` | Tracks manual coverage and performs AI-assisted gap analysis |
| Knowledge | `backend/app/knowledge` | Indexes recurring findings and provides cross-engagement trends, profiles, and recommendations |
| AI abstraction | `backend/app/ai` | Provides a common completion interface for external and local model providers |
| Web interface | `frontend/src` | Implements engagement, evidence, analysis, reporting, tool, knowledge, and settings workflows |
| Desktop entry | `run.py` | Starts the backend and opens the bundled web interface through pywebview |

## Primary data flows

### Scan to finding

1. The user uploads scanner output to an engagement.
2. A format-specific parser extracts a normalized representation.
3. The correlation engine combines evidence from supported tools.
4. The configured AI provider drafts structured findings.
5. Deduplication updates matching findings and creates new records.
6. The knowledge service indexes the resulting findings.
7. The operator reviews and edits every result.

### Active Directory analysis

1. The user uploads a SharpHound or BloodHound ZIP export.
2. The parser extracts directory objects and relationships.
3. The backend stores an import summary and graph records.
4. AI-assisted analysis proposes attack paths.
5. The operator can create findings from reviewed paths.

The strings `Enterprise Admins` and `Enterprise Key Admins` in the parser are Microsoft Active Directory group names. They are not Breachwright product editions.

### Reporting

1. The backend loads the engagement, findings, attack paths, evidence references, and selected template.
2. Optional AI assistance drafts report narrative content.
3. The report service writes Markdown or DOCX output to the application data directory.
4. An authenticated download endpoint returns the generated file.

## Trust boundaries

- AI providers receive the prompt and assessment context needed for the requested operation. Users must evaluate provider data-handling terms before sending client information.
- Local model endpoints keep model traffic within infrastructure controlled by the operator, subject to that endpoint's configuration.
- Tool Runner commands execute on the Breachwright host with the permissions of the Breachwright process.
- Evidence and report files are stored outside the source tree in the platform application data directory.
- The desktop application binds to loopback by default. Any broader network exposure requires TLS, firewall rules, and deliberate deployment hardening.

## Data and migrations

Alembic migrations in `backend/alembic/versions` define the persistent schema. Existing installations can upgrade in place. Removing the former activation subsystem does not delete assessment data or require a schema migration because activation state was stored in separate local files.
