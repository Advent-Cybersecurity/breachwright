# Security Policy

## Supported versions

Security fixes are provided for the latest 2.x release. Older releases may contain the former activation system and are not supported after the open-source release.

## Report a vulnerability

Please do not open a public issue for an unpatched vulnerability.

Use GitHub's private security advisory feature for this repository. If that is unavailable, email support@adventcybersecurity.com with:

- A clear description of the issue and its impact
- The affected version and platform
- Reproduction steps or a proof of concept
- Any suggested mitigation
- Whether the issue is already public

Do not include real customer assessment data, credentials, access tokens, or other sensitive information.

We will acknowledge receipt when capacity allows, investigate the report, and coordinate disclosure when a fix is available. This community project does not promise a specific response or remediation time.

## Operational security

Breachwright stores assessment evidence, reports, credentials for configured AI providers, and authentication data on the host where it runs. Operators are responsible for host security, backups, access control, TLS termination, network restrictions, and the handling requirements that apply to their client data.

The Tool Runner executes operator-supplied shell commands with the
operating-system permissions of the Breachwright process. Administrators and
analysts can access this function; viewers cannot. Do not create editing
accounts for untrusted people, do not expose the application directly to an
untrusted network, and review each command before execution.
