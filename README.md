# Breachwright

Breachwright is open-source penetration test management software for organizing assessment evidence, turning scanner output into reviewable findings, mapping attack paths, and producing client-ready reports.

Created by [Advent Cybersecurity](https://www.adventcybersecurity.com) and released as open source for the security community.

## Open-source release

Breachwright has one distribution with the complete product feature set. There are no paid editions, activation keys, seat limits, engagement limits, finding limits, feature gates, or subscription checks.

The former hosted Advent AI provider is not part of the open-source release because it depended on Advent-operated infrastructure and a private access service. Every AI-assisted product workflow remains available through user-controlled providers:

- Anthropic
- OpenAI
- Azure OpenAI
- AWS Bedrock
- Ollama, vLLM, llama.cpp, LM Studio, and other compatible local endpoints

Third-party AI services may charge for API usage. Local model support does not require a commercial API.

## Features

- Scan ingestion for nmap, Nessus, Burp Suite, and structured tool output
- AI-assisted finding drafts with severity, CVSS, evidence, and remediation
- Evidence-grounded AI review with source excerpts, confidence, create/update
  diffs, and accept, edit, reject, or bulk review controls
- Versioned scan snapshots with deterministic retest comparison
- Finding change history, retest scheduling, and report readiness checks
- Built-in engagement templates with automatic methodology checklists
- Current OWASP Top 10:2025 coverage for web engagements
- Dedicated OWASP API Security Top 10 (2023) checklist for API engagements
- Nuclei JSONL and SARIF 2.1 interoperability
- Versioned engagement export and import that preserves checklist progress,
  finding history, and normalized scan comparison history
- Exploitation chains and MITRE ATT&CK-aware attack narratives
- SharpHound and BloodHound ZIP import with Active Directory attack-path analysis
- Markdown and DOCX report generation
- Verified local backup and offline restore with secret exclusion
- Built-in system diagnostics and version visibility
- Evidence attachments, retest tracking, and engagement export/import
- Tool Runner workflows for nmap, nikto, subfinder, feroxbuster, nuclei, and related tools
- PTES, OWASP, and NIST methodology checklists and gap analysis
- Cross-engagement intelligence, client risk profiles, and recurring-finding analysis
- Custom report templates and AI prompts
- Immediate access to one local owner workspace with no account or login setup
- Light and dark themes

OWASP Top 10 checklists are practical baselines, not claims of complete test
coverage. Use a scope-appropriate verification standard and methodology for the
full assessment.

## Local application security

Breachwright can execute security tools and process sensitive assessment data. Use it only on systems and data you are authorized to test. Review Tool Runner commands before execution, protect the application data directory, and do not expose the API directly to untrusted networks.

Breachwright is designed as a single-owner local desktop tool. It opens
directly into the workspace without accounts, passwords, roles, or sessions.
The packaged application binds only to the local machine. Anyone who can use
the operating-system account can access Breachwright data and run its tools,
so rely on workstation login, disk encryption, and file permissions.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and supported versions.

## Install from source

### Requirements

- Python 3.11 or newer
- Node.js 18 or newer
- GTK3 and WebKit2 on Linux when using the desktop window
- Edge WebView2 on Windows when using the desktop application
- Any external assessment tools you want to invoke through Tool Runner

### Linux and macOS

```bash
git clone https://github.com/Advent-Cybersecurity/breachwright.git
cd breachwright
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
python run.py
```

### Windows PowerShell

```powershell
git clone https://github.com/Advent-Cybersecurity/breachwright.git
Set-Location breachwright
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Set-Location frontend
npm ci
npm run build
Set-Location ..
python run.py
```

On first launch, Breachwright opens directly into the local workspace.

## Windows and Linux packages

Breachwright uses one source tree, one feature set, and one data format on
Windows and Linux. Native desktop dependencies differ, so release candidates
are produced as two archives:

- Windows x64 ZIP with `Breachwright.exe` and `BreachwrightCLI.exe`
- Linux x64 tar.gz with `Breachwright` and `BreachwrightCLI`

Both archives are built and tested by the same candidate workflow. A release
download is not updated until both native candidates pass their platform
checks. See [INSTALL.md](INSTALL.md) for extraction, installation, first-run,
data-location, backup, and uninstall instructions.

## Configure an AI provider

The application stores configuration in its platform-specific data directory:

- Windows: `%APPDATA%\Breachwright\.env`
- macOS: `~/Library/Application Support/Breachwright/.env`
- Linux source or direct bundle: `${XDG_DATA_HOME:-~/.local/share}/breachwright/.env`
- Linux installed package: `${XDG_DATA_HOME:-~/.local/share}/breachwright/data/.env`

You can configure Anthropic, OpenAI, or a local model in the Settings page. Azure OpenAI and AWS Bedrock can be configured through the environment file. Start with [.env.example](.env.example).

AI configuration is optional for manual findings, evidence management, checklists, reporting from existing content, export/import, and other non-AI workflows.

Engagement JSON exports are intended for sharing editable project records and
normalized comparison history. They do not include raw scan files, binary
evidence attachments, Active Directory datasets, pending AI proposals,
generated reports, or Tool Runner output. Use a verified full backup when
moving or preserving an entire local workspace.

AI output is treated as untrusted. Scan and Active Directory analysis create
review proposals rather than accepted findings. Each supported proposal cites
stored evidence, and nothing enters the Findings list until the local operator
accepts it. See [docs/AI_TRUST_AND_EVALUATION.md](docs/AI_TRUST_AND_EVALUATION.md).

## Back up and restore data

Create and download verified local backups from the Settings page. Backups
include the SQLite database, evidence, uploads, reports, custom template
assets, and Tool Runner output. API keys and environment configuration are
excluded.

Restores are offline by design and preserve displaced data in a recovery
folder. See [docs/DATA_SAFETY.md](docs/DATA_SAFETY.md) for packaged and source
commands.

## Docker

The included Docker Compose configuration runs the API, PostgreSQL, and the web frontend:

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD in .env before continuing.
docker compose up --build
```

The Docker deployment listens only on `127.0.0.1:80` by default. Application
files persist in `./data`; PostgreSQL data persists in the `pgdata` volume.
The built-in portable backup currently supports SQLite installations, so
Docker/PostgreSQL users must back up both PostgreSQL and `./data`. Do not
change the loopback binding unless you add a separate, deliberate access
control and transport-security layer.

## Architecture

- Backend: FastAPI, SQLAlchemy, Alembic, SQLite or PostgreSQL
- Frontend: React, Vite, Tailwind CSS
- Desktop: pywebview
- Reports: python-docx and Markdown
- Packaging: PyInstaller for Windows and Linux

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the system map and data flows. The current dependency advisory assessment is in [docs/DEPENDENCY_SECURITY.md](docs/DEPENDENCY_SECURITY.md).

## Contributing

Issues and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change. Community support expectations are described in [SUPPORT.md](SUPPORT.md).

The project direction, cross-platform release standards, and cost and privacy
guardrails are documented in [ROADMAP.md](ROADMAP.md).

## License and attribution

Breachwright is licensed under the [Apache License 2.0](LICENSE).

Copyright 2026 Advent Cybersecurity LLC.

The Apache License permits use, modification, and redistribution under its terms. It does not grant permission to use Advent Cybersecurity trademarks or imply endorsement. See [NOTICE](NOTICE), [TRADEMARKS.md](TRADEMARKS.md), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
