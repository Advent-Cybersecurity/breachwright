# Breachwright architecture

## Product boundary

Breachwright is a local-first penetration test management application. It combines a FastAPI backend, a React interface, and an optional desktop window. The same backend can use SQLite for a single-host installation or PostgreSQL in the Docker deployment.

All application capabilities are part of the open-source distribution. There is no activation, entitlement, seat, engagement, or finding-limit service.

## Major components

| Area | Location | Responsibility |
| --- | --- | --- |
| API composition | `backend/app/main.py` | Starts the service, runs migrations, registers routers, exposes health and update checks, and serves the built frontend |
| Local ownership | `backend/app/auth` | Maintains one internal owner record so existing database relationships remain compatible; no login or account API is exposed |
| Engagement data | `backend/app/engagements` | Engagements, findings, attack paths, reports, scans, settings, export, and import |
| Assessment workflow | `backend/app/workflow` | Scan snapshots, asset and service inventory, retest work, readiness, recent activity, local search, deterministic exports, and assessment templates |
| Scan analysis | `backend/app/analysis` | Uploads scan data, previews bounded selected input without provider use, calls the configured AI provider, and stores grounded review drafts |
| Correlation | `backend/app/correlation` | Normalizes structured output from several tools and correlates hosts and findings |
| Active Directory | `backend/app/ad` | Parses SharpHound and BloodHound ZIP exports and creates attack-path data |
| Attack paths | `backend/app/attack_paths` | Generates exploitation chains from engagement findings |
| Narratives | `backend/app/narrative` | Produces path-level and engagement-level assessment narratives |
| Reports | `backend/app/reports` | Generates Markdown and DOCX reports and manages custom templates |
| Evidence | `backend/app/findings/evidence.py` and `backend/app/findings/notebook_router.py` | Stores validated finding attachments plus pre-finding notes and notebook attachments |
| Tool Runner | `backend/app/jobs` | Launches operator-supplied local commands, captures bounded output and structured artifacts, and lets completed results enter Scans or the Evidence Notebook |
| Methodologies | `backend/app/checklists` and `backend/app/gap_detection` | Tracks manual coverage and performs AI-assisted gap analysis |
| Knowledge | `backend/app/knowledge` | Indexes recurring findings and provides cross-engagement trends, profiles, and recommendations |
| AI abstraction | `backend/app/ai` | Provides provider-neutral completion, bounded repair, structured validation, and deterministic quality metrics |
| Data safety | `backend/app/system` | Verifies backups, restores SQLite workspaces, and reports database plus bounded stored-file integrity checks |
| Web interface | `frontend/src` | Implements engagement, evidence, analysis, reporting, tool, knowledge, and settings workflows |
| Desktop entry | `run.py` | Starts the backend and opens the bundled web interface through pywebview |

## Primary data flows

### Scan to finding

1. The user uploads scanner output to an engagement.
2. A format-specific parser extracts a normalized representation.
3. The correlation engine combines evidence from supported tools.
4. The configured AI provider drafts structured findings.
5. Unsupported evidence references cause a proposal to be discarded.
6. Deduplication marks each grounded proposal as a create or update draft.
7. The operator accepts, edits, or rejects every draft.
8. Only accepted drafts become findings and enter the knowledge index.

An operator can also review a normalized scanner observation directly into a
finding without calling an AI provider. Breachwright prevents a second finding
from being created from the same observation and records the source snapshot
and observation identifiers in finding history.

### Active evidence workspace

1. An explicitly selected scan upload becomes an immutable normalized
   snapshot.
2. The latest snapshot drives an asset and service inventory. Finding,
   evidence, and retest links are derived from existing records rather than
   copied into a separate asset database.
3. Raw analyst notes and validated attachments can be stored in the Evidence
   Notebook before they meet the finding standard.
4. An operator can review a notebook note into a finding. Its note and
   attachment provenance is retained, and the linked note becomes immutable.
5. Local workspace search and the Overview read from the same engagement
   records without sending data to an external service.

### Tool Runner reuse

1. The operator reviews and starts a local command for an engagement.
2. Breachwright captures a bounded output tail and recognizes bounded Nmap or
   Nuclei artifact files written by its presets.
3. Any terminal job can be preserved as a notebook note.
4. A successfully completed structured Nmap or Nuclei job can be copied into
   Scans exactly once, without an AI call.
5. Deleting the originating job does not delete the copied scan upload.

### Active Directory analysis

1. The user uploads a SharpHound or BloodHound ZIP export.
2. The parser extracts directory objects and relationships.
3. The backend stores an import summary and graph records.
4. AI-assisted analysis proposes paths using exact directory object and
   relationship evidence IDs.
5. Unsupported nodes and evidence references are rejected.
6. Finding suggestions enter the same review workbench used by scan analysis.

The strings `Enterprise Admins` and `Enterprise Key Admins` in the parser are Microsoft Active Directory group names. They are not Breachwright product editions.

### Reporting

1. The backend loads the engagement, findings, attack paths, evidence references, and selected template.
2. Optional AI assistance drafts report narrative content.
3. The report service writes Markdown or DOCX output to the application data directory.
4. The local API returns the generated file.

## Trust boundaries

- AI providers receive the prompt and assessment context needed for the requested operation. Common credential patterns are redacted locally by default, but this is not a substitute for operator review. Users must evaluate provider data-handling terms before sending client information.
- Uploaded scanner, finding, directory, and report content is delimited as
  untrusted data. Model output remains untrusted until schema, size, and
  citation validation completes.
- AI analysis uses explicit context and chunk limits. Tests use fake providers
  and sanitized fixtures and never contact paid models.
- Local model endpoints keep model traffic within infrastructure controlled by the operator, subject to that endpoint's configuration.
- Tool Runner commands execute on the Breachwright host with the permissions of the Breachwright process.
- Evidence and report files are stored outside the source tree in the platform application data directory.
- Finding attachments, notebook attachments, scan uploads, reports, templates,
  and Tool Runner artifacts are included in verified SQLite workspace backups.
  Environment files and API keys are excluded.
- The desktop application and included Docker web port bind to loopback. Breachwright has no application login, so it must not be exposed to a network.

## Data and migrations

Alembic migrations in `backend/alembic/versions` define the persistent schema.
Existing installations can upgrade in place. The earliest existing
administrator remains the internal local owner so engagement and finding
ownership relationships do not change. Other legacy user rows remain only for
database compatibility and are not exposed as accounts.
