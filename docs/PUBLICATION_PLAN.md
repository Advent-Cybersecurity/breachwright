# Public repository publication plan

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

## Recommended topology

1. Keep the existing repository private as the internal legacy archive.
2. Rename it to a clearly private archival name such as
   `breachwright-legacy-private`.
3. Create a new `Advent-Cybersecurity/breachwright` repository with a clean root
   commit containing only the reviewed 2.0.0 source.
4. Enable branch protection, secret scanning, push protection, private
   vulnerability reporting, Dependabot, and code scanning before accepting
   community contributions.
5. Publish the first public release as `v2.0.0` with newly built source and
   binary artifacts. Do not copy legacy release assets into the public
   repository.
6. Keep `breachwright-dev` private until its unique refs are checked, then
   archive it to avoid confusion with the community repository.

## Required approvals

No repository rename, creation, visibility change, tag, release, archive, or
website deployment should occur until Advent Cybersecurity approves this
topology and confirms rights to publish every source file and bundled brand
asset.
