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
- Exploitation chains and MITRE ATT&CK-aware attack narratives
- SharpHound and BloodHound ZIP import with Active Directory attack-path analysis
- Markdown and DOCX report generation
- Evidence attachments, retest tracking, and engagement export/import
- Tool Runner workflows for nmap, nikto, subfinder, feroxbuster, nuclei, and related tools
- PTES, OWASP, and NIST methodology checklists and gap analysis
- Cross-engagement intelligence, client risk profiles, and recurring-finding analysis
- Custom report templates and AI prompts
- Multi-user roles with no application-enforced seat limit
- Light and dark themes

## Security and authorization

Breachwright can execute security tools and process sensitive assessment data. Use it only on systems and data you are authorized to test. Review Tool Runner commands before execution, protect the application data directory, and do not expose the API directly to untrusted networks.

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

On first launch, Breachwright guides you through creating the initial administrator account.

## Configure an AI provider

The application stores configuration in its platform-specific data directory:

- Windows: `%APPDATA%\Breachwright\.env`
- macOS: `~/Library/Application Support/Breachwright/.env`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/breachwright/.env`

You can configure Anthropic, OpenAI, or a local model in the Settings page. Azure OpenAI and AWS Bedrock can be configured through the environment file. Start with [.env.example](.env.example).

AI configuration is optional for manual findings, evidence management, checklists, reporting from existing content, export/import, and other non-AI workflows.

## Docker

The included Docker Compose configuration runs the API, PostgreSQL, and the web frontend:

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD in .env before continuing.
docker compose up --build
```

The Docker deployment listens on port 80 by default. Review authentication, TLS termination, network exposure, backups, and secret management before using it with real assessment data.

## Architecture

- Backend: FastAPI, SQLAlchemy, Alembic, SQLite or PostgreSQL
- Frontend: React, Vite, Tailwind CSS
- Desktop: pywebview
- Reports: python-docx and Markdown
- Packaging: PyInstaller for Windows and Linux

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the system map and data flows. The current dependency advisory assessment is in [docs/DEPENDENCY_SECURITY.md](docs/DEPENDENCY_SECURITY.md).

## Contributing

Issues and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change. Community support expectations are described in [SUPPORT.md](SUPPORT.md).

## License and attribution

Breachwright is licensed under the [Apache License 2.0](LICENSE).

Copyright 2026 Advent Cybersecurity LLC.

The Apache License permits use, modification, and redistribution under its terms. It does not grant permission to use Advent Cybersecurity trademarks or imply endorsement. See [NOTICE](NOTICE), [TRADEMARKS.md](TRADEMARKS.md), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
