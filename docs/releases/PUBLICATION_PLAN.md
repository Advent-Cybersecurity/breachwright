# Public repository publication record

## Publication status

Advent Cybersecurity approved and completed the clean-history publication on
July 28, 2026 PDT.

- Public repository: <https://github.com/Advent-Cybersecurity/breachwright>
- Public root commit: `4403c01f686cd67f2ecdc0a6758bf52ef7f28777`
- Public release: <https://github.com/Advent-Cybersecurity/breachwright/releases/tag/v2.0.0>
- Legacy history and releases: preserved in the private
  `Advent-Cybersecurity/Archive` repository; the former
  `Advent-Cybersecurity/breachwright-legacy-private` repository was deleted
  after its contents were verified there on November 26, 2026 EST.
- Duplicate development repository: verified against the legacy repository's
  Git tree, retained privately, and archived as
  `Advent-Cybersecurity/breachwright-dev`
- Website: <https://www.adventcybersecurity.com/software/breachwright>

The `v2.0.0` release is source-only until packaged binaries complete supported
platform smoke testing. The annotated tag is unsigned because no release
signing identity was configured in the publication environment.

## Finding

The existing private `Advent-Cybersecurity/breachwright` repository contains
historical licensing code, tier-specific release titles, tags from `v1.2.0`
through `v1.7.2`, and downloadable binaries built before the open-source
conversion. Making that repository public would expose all reachable commits,
tags, and release assets and would preserve product-tier references that are not
part of Breachwright 2.0.0.

The reachable Git history and current prepared source were scanned with
Gitleaks 8.30.1 with no detected secrets. The issue is product history and
legacy distribution state, not a detected credential leak.

## Initial implemented topology (July 28, 2026)

1. Keep the existing repository private as the internal legacy archive.
2. Rename it to a clearly private archival name such as
   `breachwright-legacy-private`.
3. Create a new `Advent-Cybersecurity/breachwright` repository with a clean root
   commit containing only the reviewed 2.0.0 source.
4. Enable branch protection, secret scanning, push protection, private
   vulnerability reporting, Dependabot, and code scanning before accepting
   community contributions.
5. Publish the first public release as `v2.0.0` with GitHub-generated source
   archives. Do not copy legacy release assets into the public repository.
6. Verify `breachwright-dev` has no unique branches, tags, releases, or Git
   tree, then keep it private and archive it.

## Approval record

Advent Cybersecurity approved the repository and website publication sequence
before any repository rename, public repository creation, release, archive, or
production website change was performed.

## Subsequent archive consolidation (November 26, 2026 EST)

The private `breachwright-legacy-private` and `breachwright-dev` repositories
were copied into `Advent-Cybersecurity/Archive` as browsable default-branch
snapshots, complete Git bundles, and GitHub metadata exports. The legacy
repository's eight releases and nine attached binaries were also copied to
namespaced releases in Archive. The copied binary sizes and SHA-256 digests
matched their source release assets, and the Git refs and snapshots were
verified from a fresh Archive clone.

After verification, `breachwright-legacy-private` was deleted. Its former
repository and release URLs no longer resolve; authorized users can retrieve
the source history, original tags, release notes, and binaries from the private
Archive repository. `breachwright-dev` remains private and read-only at its
original URL.
