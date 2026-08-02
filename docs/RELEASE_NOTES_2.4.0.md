# Breachwright 2.4.0

Breachwright 2.4 modernizes optional AI provider setup and compatibility while
preserving the complete local assessment workspace introduced in 2.3. Advent
Cybersecurity created Breachwright and releases the complete application as
open-source software for the security community. Windows and Linux packages
contain the same feature set, with no accounts, activation, paid editions,
seat limits, or feature gates.

## Easier hosted-provider setup

- Anthropic and OpenAI setup is now API-key-first. Breachwright selects its
  tested recommendation automatically and shows the exact selection in
  Settings.
- An Advanced section retains an exact model override for operators who need a
  different provider model.
- Existing default Claude Sonnet 4 and GPT-4o settings migrate to the current
  recommendation. Explicit custom model choices remain unchanged.
- OpenAI GPT-5-family models use the Responses API, while explicit legacy
  model overrides retain Chat Completions compatibility.
- Claude 5 requests avoid sampling controls that conflict with the provider's
  adaptive-thinking behavior. Explicit older Claude model overrides retain
  their prior sampling behavior.

## Azure, Bedrock, and local providers

- Azure OpenAI uses the stable v1 API by default. Explicit dated API versions
  remain supported for existing deployments.
- Amazon Bedrock requires an explicit model or inference-profile identifier
  because availability differs by AWS region.
- Local OpenAI-compatible providers require an installed model selection
  instead of assuming that a particular model exists.
- OpenAI and Anthropic client libraries are updated for these provider paths.

## Maintenance and release safety

- Frontend build tooling received compatible Autoprefixer and PostCSS updates.
- Application server launch paths no longer initialize an unused WebSocket
  protocol implementation.
- Repository documentation and historical release records are easier to find.
- Dependency updates are grouped by ecosystem and compatibility risk.
- Native candidate packaging remains a manual release action. Windows and
  Linux candidates must both pass before public downloads change.
- The upgrade gate now verifies legacy engagement data, finding data, local
  reporting, removed authentication routes, and saved provider configuration.
- AI remains optional. Core assessment, evidence, reporting, export, backup,
  restore, and scanner-correlation workflows do not require a provider.

## Downloads

- `breachwright-2.4.0-windows-x64.zip`
- `breachwright-2.4.0-linux-x64.tar.gz`
- `SHA256SUMS.txt`

Verify the published SHA-256 checksum before installation. macOS remains a
source installation until it has the same repeatable native build, desktop,
installation, and signing gates.

The Windows executables are not currently Authenticode-signed. Windows may
show an unknown-publisher or Microsoft Defender SmartScreen warning. Download
only from the official Advent Cybersecurity GitHub release and do not run the
files if their SHA-256 values differ from `SHA256SUMS.txt`.

Back up the workspace from **Settings > Data Safety** before upgrading. The
2.4 release adds no database migration. Existing workspaces retain their local
data and saved provider configuration. Read `INSTALL.md`,
`docs/DATA_SAFETY.md`, and `SECURITY.md` for platform paths, restore
procedures, and the single-owner local security model.

Using a commercial AI provider can incur charges from that provider. The
Breachwright application, its complete feature set, and its local workflows
remain free and open source.
