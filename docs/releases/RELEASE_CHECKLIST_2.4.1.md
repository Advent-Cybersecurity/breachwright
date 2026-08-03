# Breachwright 2.4.1 release checklist

This checklist controls the Windows download-origin startup hotfix. Evidence
must refer to the exact release commit and both supported native platforms.

## Product and safety gates

- [x] The complete feature set remains available without accounts or paid gates
- [x] The hotfix preserves Windows download-origin metadata
- [x] Both Windows executables receive the required .NET runtime configuration
- [x] Desktop smoke testing requires an actual shown application window
- [x] The Windows candidate reproduces internet-zone DLL marking
- [x] Core assessment, reporting, backup, restore, and scanner workflows remain unchanged
- [x] Candidate workflows use public GitHub-hosted runners and call no paid AI service
- [x] Windows unsigned-binary guidance and checksum verification remain prominent

Pre-publication local evidence on 2026-08-03 includes 135 strict source tests,
backend compilation, workflow YAML parsing, the packaged end-to-end journey,
normal and internet-zone-marked Windows desktop launches, isolated install and
uninstall with data preservation, and Windows archive verification. This local
evidence does not replace the exact-commit native runner gates below.

## Exact-release gates

- [x] Windows and Ubuntu source suites pass for the v2.4.1 commit
- [x] Frontend production audit and build pass for the v2.4.1 commit
- [x] Python and JavaScript CodeQL analysis passes for the v2.4.1 commit
- [x] Windows package, desktop, marked-download, install, uninstall, upgrade, and archive tests pass
- [x] Linux package, desktop, install, uninstall, upgrade, and archive tests pass
- [x] Retained Windows and Linux archives match the exact tested commit
- [x] `SHA256SUMS.txt` contains the reviewed digest of each published native archive
- [x] The GitHub release and Advent website point to the same v2.4.1 assets

## Publication evidence

The exact release commit is
`d6fadac6a0d3c8bfd68f7970573761d3dd0452cf`. Main CI run
[`30854231109`](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30854231109)
passed the Windows, Ubuntu, and frontend jobs. Main CodeQL run
[`30854231119`](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30854231119)
passed Python and JavaScript/TypeScript analysis.

Retained candidate run
[`30854259455`](https://github.com/Advent-Cybersecurity/breachwright/actions/runs/30854259455)
passed all required native gates from that commit. The reviewed archive
digests are:

- Windows: `ad12c49263bc9e29f0702978a5a1e73d4b132a1e7a79f9f049bdf20fc214d918`
- Linux: `b7eca4380e98eda0ba6ee527fa4c6cdb58af6b4cebb10ff660e16adc08e27187`

GitHub release
[`v2.4.1`](https://github.com/Advent-Cybersecurity/breachwright/releases/tag/v2.4.1)
is public and records matching SHA-256 digests for both archives. Advent
website pull request
[`#3`](https://github.com/Advent-Cybersecurity/advent-website/pull/3)
merged as `83ad7ec1d8f1f1a1fd254164ba61b5382f28f098`. On 2026-08-03,
the [production product page](https://www.adventcybersecurity.com/software/breachwright?release=2.4.1),
release page, Windows archive, Linux archive, and checksum file all returned
HTTP 200. The rendered product page contained the v2.4.1 version, all three
asset links, and the Windows startup hotfix explanation.

Do not publish if a supported platform fails, the retained artifact commit does
not match the release commit, or an unexpected dependency advisory appears.
