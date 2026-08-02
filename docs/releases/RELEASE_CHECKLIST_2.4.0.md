# Breachwright 2.4.0 release checklist

This checklist controls the AI-provider compatibility release. Evidence must
refer to the exact release commit and both supported native platforms.

## Product and safety gates

- [x] The complete feature set remains available without accounts or paid gates
- [x] Anthropic and OpenAI API-key-first setup passes with tested defaults and explicit overrides
- [x] Claude 5, GPT-5 Responses, Azure v1, legacy override, Bedrock, and local validation paths have regression coverage
- [x] Core engagement, evidence, reporting, export, backup, restore, and scanner workflows pass without an AI provider
- [x] Upgrade validation preserves an existing v2 workspace and provider configuration
- [x] Candidate workflows use public GitHub-hosted runners and call no paid AI service
- [x] Windows unsigned-binary guidance and checksum verification remain prominent

Pre-publication local evidence on 2026-08-02 includes 134 strict source tests,
the frontend production build, the clean Windows builder and packaged journey,
archive verification, desktop launch, install and uninstall data preservation,
and the v2.0.0-to-v2.4.0 upgrade test. This local evidence does not replace the
exact-commit native runner gates below.

## Exact-release gates

- [ ] Windows and Ubuntu source suites pass for the v2.4.0 commit
- [ ] Frontend production audit and build pass for the v2.4.0 commit
- [ ] Python and JavaScript CodeQL analysis passes for the v2.4.0 commit
- [ ] Windows package, desktop, install, uninstall, upgrade, and archive tests pass
- [ ] Linux package, desktop, install, uninstall, upgrade, and archive tests pass
- [ ] Retained Windows and Linux archives match the exact tested commit
- [ ] `SHA256SUMS.txt` contains the reviewed digest of each published native archive
- [ ] The GitHub release and Advent website point to the same v2.4.0 assets

Do not publish if a supported platform fails, the retained artifact commit does
not match the release commit, or an unexpected dependency advisory appears.
