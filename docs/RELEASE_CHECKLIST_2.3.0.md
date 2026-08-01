# Breachwright 2.3.0 release checklist

This checklist controls the active-assessment workspace release. Evidence must
refer to the exact release commit and both supported native platforms.

## Product and safety gates

- [x] The complete feature set remains available without accounts or paid gates
- [x] Overview, search, asset inventory, retest views, and Evidence Notebook pass end to end
- [x] Scanner auto-detection, no-AI promotion, Tool Runner reuse, CSV, and SARIF pass end to end
- [x] AI context limits, redaction preflights, citations, and safe provider failures have regression coverage
- [x] Backup, validation, restore, diagnostics, support snapshot, and data-preserving uninstall pass
- [x] Tool Runner presets reject injection-shaped input before process creation
- [x] Non-loopback Host headers and occupied local ports are rejected
- [x] Source installation validates Node.js 20 and honors the npm lockfile
- [x] Candidate workflows use public GitHub-hosted runners and call no paid AI service

## Exact-release gates

- [ ] Windows and Ubuntu source suites pass for the v2.3.0 commit
- [ ] Frontend production audit and build pass for the v2.3.0 commit
- [ ] Python and JavaScript CodeQL analysis passes for the v2.3.0 commit
- [ ] Windows package, desktop, install, uninstall, upgrade, and archive tests pass
- [ ] Linux package, desktop, install, uninstall, upgrade, and archive tests pass
- [ ] Retained Windows and Linux archives match the exact tested commit
- [ ] SHA256SUMS contains the reviewed digest of each published native archive
- [ ] The GitHub release and Advent website point to the same v2.3.0 assets

Do not publish if a supported platform fails, the retained artifact commit does
not match the release commit, or an unexpected dependency advisory appears.
