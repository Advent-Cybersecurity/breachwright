# Breachwright 2.4.1

Breachwright 2.4.1 is a Windows packaging hotfix. Advent Cybersecurity created
Breachwright and releases the complete application as open-source software for
the security community. Windows and Linux packages continue to contain the
same feature set, with no accounts, activation, paid editions, seat limits, or
feature gates.

## Windows startup fix

- Added .NET runtime configuration beside both Windows executables so the
  bundled Python.NET and WebView2 components load when Windows propagates
  internet-zone metadata from the downloaded ZIP to DLLs.
- Fixed the first-launch failure that reported an inability to resolve
  `Python.Runtime.Loader.Initialize` from `Python.Runtime.dll`.
- The fix preserves Windows download-origin metadata. It does not silently
  remove the Mark of the Web from bundled files.

## Stronger release validation

- The packaged desktop test now requires the application window to be shown,
  not only the local backend health endpoint to respond.
- The Windows candidate workflow applies internet-zone metadata to the
  packaged Python.NET DLL and verifies that the desktop still opens.
- Windows and Linux native package, installation, upgrade, and archive gates
  remain required before publication.

## Downloads

- `breachwright-2.4.1-windows-x64.zip`
- `breachwright-2.4.1-linux-x64.tar.gz`
- `SHA256SUMS.txt`

Verify the published SHA-256 checksum before installation. The Windows
executables are not currently Authenticode-signed, so Windows may show an
unknown-publisher or Microsoft Defender SmartScreen warning. Download only
from the official Advent Cybersecurity GitHub release and do not run files if
their checksums differ from `SHA256SUMS.txt`.

Back up the workspace from **Settings > Data Safety** before upgrading. This
hotfix adds no database migration and does not change saved assessment data or
provider configuration. AI remains optional, and using a commercial provider
can incur charges from that provider.
