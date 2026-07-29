# Breachwright 2.0.0

Breachwright was created by Advent Cybersecurity and is now fully open source
for the security community under the Apache License 2.0.

## One complete distribution

Version 2.0.0 removes product editions, activation keys, subscription checks,
seat limits, engagement limits, finding limits, and feature gates. Every
Breachwright product feature is included in the open-source distribution.

Included capabilities cover:

- Engagement, finding, evidence, retest, checklist, and report management
- AI-assisted scan analysis, attack paths, narratives, and remediation guidance
- SharpHound and BloodHound analysis
- Markdown and DOCX reporting
- Tool Runner workflows
- Engagement export and import
- Custom prompts and report templates
- Cross-engagement knowledge and methodology gap analysis

## AI providers

AI-assisted workflows can use Anthropic, OpenAI, Azure OpenAI, AWS Bedrock, or
local and self-hosted OpenAI-compatible endpoints such as Ollama and vLLM.

The former Moxie provider is not included because it depended on a private
Advent-operated service. No open-source workflow depends on Advent-hosted
infrastructure.

## Security and maintenance

- Evidence and report files now require authenticated downloads.
- Access tokens are no longer placed in download URLs.
- Vulnerable Python authentication and framework dependencies were replaced or
  upgraded.
- CI, dependency audits, CodeQL, Dependabot, and open-source invariant tests
  are included.
- Community security reporting and disclosure guidance is available in
  `SECURITY.md`.

## Installation

```bash
git clone https://github.com/Advent-Cybersecurity/breachwright.git
cd breachwright
python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
python run.py
```

Docker deployment instructions and AI provider configuration are documented in
the repository README.

## Release artifacts

This initial public release is source-only. GitHub provides automatic source
archives for the tag. Windows and Linux binary packages will be added only
after platform-specific packaging and smoke tests pass. Legacy licensed binaries
are not part of this release.
