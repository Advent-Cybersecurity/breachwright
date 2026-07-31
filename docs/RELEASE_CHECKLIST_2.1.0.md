# Breachwright 2.1.0 release checklist

This checklist controls the first binary release after Breachwright became
fully open source.

## Hard release gates

- [ ] All source tests pass on `windows-latest`
- [ ] All source tests pass on `ubuntu-latest`
- [ ] Frontend production build and release audit pass
- [ ] Windows candidate builds from a clean checkout
- [ ] Linux candidate builds from a clean checkout
- [x] Windows packaged first-run and core user journey pass
- [ ] Linux packaged first-run and core user journey pass
- [x] Windows desktop window smoke test passes
- [ ] Linux GTK and WebKit desktop window smoke test passes
- [x] Backup creation, validation, download, restore, and rollback pass
- [x] Markdown and DOCX reports generate without an AI key
- [x] Upgrade from a copy of a v2.0.0 SQLite database succeeds
- [ ] Candidate archives contain the license, notices, documentation, and CLI
- [ ] Dependency audits and CodeQL have no unexplained release blockers
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
- [x] A database created by the v2.0.0 source upgrades with its account, engagement, and finding intact
- [x] Browser setup, login, engagement, finding, DOCX report, diagnostics, and backup flows passed
- [x] The public v2.0.0 source release remains unchanged

Linux and clean-checkout gates remain open until the GitHub-hosted candidate
workflow completes.
