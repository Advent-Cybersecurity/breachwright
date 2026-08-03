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

- [ ] Windows and Ubuntu source suites pass for the v2.4.1 commit
- [ ] Frontend production audit and build pass for the v2.4.1 commit
- [ ] Python and JavaScript CodeQL analysis passes for the v2.4.1 commit
- [ ] Windows package, desktop, marked-download, install, uninstall, upgrade, and archive tests pass
- [ ] Linux package, desktop, install, uninstall, upgrade, and archive tests pass
- [ ] Retained Windows and Linux archives match the exact tested commit
- [ ] `SHA256SUMS.txt` contains the reviewed digest of each published native archive
- [ ] The GitHub release and Advent website point to the same v2.4.1 assets

## Publication evidence

Record the exact release commit, protected CI and CodeQL runs, retained native
candidate run, reviewed checksums, GitHub release, website pull request, and
production HTTP verification here before closing the release sequence.

Do not publish if a supported platform fails, the retained artifact commit does
not match the release commit, or an unexpected dependency advisory appears.
