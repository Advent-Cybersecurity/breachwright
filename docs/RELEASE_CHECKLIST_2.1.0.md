# Breachwright 2.1.0 release checklist

This checklist controls the first binary release after Breachwright became
fully open source.

## Hard release gates

- [x] All source tests pass on `windows-latest`
- [x] All source tests pass on `ubuntu-latest`
- [x] Frontend production build and release audit pass
- [x] Windows candidate builds from a clean checkout
- [x] Linux candidate builds from a clean checkout
- [x] Windows packaged first-run and core user journey pass
- [x] Linux packaged first-run and core user journey pass
- [x] Windows desktop window smoke test passes
- [x] Linux GTK and WebKit desktop window smoke test passes
- [x] Backup creation, validation, download, restore, and rollback pass
- [x] Markdown and DOCX reports generate without an AI key
- [x] Upgrade from a copy of a v2.0.0 SQLite database succeeds
- [x] Candidate archives contain the license, notices, documentation, and CLI
- [x] Dependency audits and CodeQL have no unexplained release blockers
- [ ] Release archives and checksums are reviewed before publication

## Cost gate

- [x] Repository is public
- [x] GitHub Actions organization budget is $0 with usage stopping at the limit
- [x] Candidate workflows use only standard GitHub-hosted runners
- [x] No paid AI provider is called by tests
- [x] No cloud application infrastructure is required
- [x] Candidate workflow does not publish or retain binary artifacts

## Current local evidence

As of 2026-07-30:

- [x] Windows source user journey passes against a fresh SQLite database
- [x] Windows packaged v2.1.0-rc.1 user journey passes after the final local changes
- [x] Windows packaged backup and offline restore pass after the final local changes
- [x] Windows desktop window smoke test passes
- [x] Windows native install, version, uninstall, and data preservation pass
- [x] Packaged AWS Bedrock provider initializes without making a model request
- [x] A database created by the v2.0.0 source upgrades with its account, engagement, and finding intact
- [x] Browser setup, login, engagement, finding, DOCX report, diagnostics, and backup flows passed
- [x] Docker Compose configuration and persistent application data mapping pass
- [x] GitHub-hosted Linux packaged journey, desktop window, native install, and archive gates pass
- [x] The public v2.0.0 source release remains unchanged

Remote evidence for application candidate `0a49dda`:

- [CI and dependency audits](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30606345888)
- [CodeQL](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30606345897)
- [Windows and Linux candidate build](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30606345894)

Remote evidence for the documentation-complete candidate `6d9fcc0`:

- [CI and dependency audits](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30606527810)
- [CodeQL](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30606527830)
- [Windows and Linux candidate build](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30606527807)

Only deliberate review of the final release archives and checksums remains
before publication.
