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

- [x] Windows and Ubuntu source suites pass for the v2.4.0 commit
- [x] Frontend production audit and build pass for the v2.4.0 commit
- [x] Python and JavaScript CodeQL analysis passes for the v2.4.0 commit
- [x] Windows package, desktop, install, uninstall, upgrade, and archive tests pass
- [x] Linux package, desktop, install, uninstall, upgrade, and archive tests pass
- [x] Retained Windows and Linux archives match the exact tested commit
- [x] `SHA256SUMS.txt` contains the reviewed digest of each published native archive
- [x] The GitHub release and Advent website point to the same v2.4.0 assets

## Publication evidence

Release commit `2b65186997b43bb1968c8a960990554c132ebb6a` passed exact-main
[CI run 30747281535](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30747281535)
and
[CodeQL run 30747281525](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30747281525).
Retained
[candidate run 30747334782](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30747334782)
passed both native jobs from the same commit. Each job verified the v2.0
upgrade, packaged journey, desktop launch, native install and uninstall, and
release archive before retaining its archive for one day.

The reviewed SHA-256 values published in `SHA256SUMS.txt` are:

- Windows: `37b0c708d6faad5df9358dd4ef63c2bed30664287ee5f97357b1ffd6278a8e4d`
- Linux: `17e4100d4d6d2605c5e5ea1ef5ce2b0aae8f8cafa8d3977fbf8cf79653bfebfc`

GitHub release
[`v2.4.0`](https://github.com/Advent-Cybersecurity/breachwright/releases/tag/v2.4.0)
was published from that release commit. Advent website pull request
[`#2`](https://github.com/Advent-Cybersecurity/advent-website/pull/2) merged as
website commit `a8c369216d56b63c67be73d4fb208bf9dd47618b`. The public product
page served the 2.4.0 version and exact Windows, Linux, checksum, and release
links with HTTP 200 responses on 2026-08-02.

Do not publish if a supported platform fails, the retained artifact commit does
not match the release commit, or an unexpected dependency advisory appears.
