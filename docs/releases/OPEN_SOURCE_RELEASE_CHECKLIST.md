# Open-source release checklist

This checklist is for the first public Breachwright release.

## Code and product

- [x] Remove remote activation and signed entitlement validation
- [x] Remove all backend feature gates
- [x] Remove all frontend upgrade gates and edition banners
- [x] Remove seat, engagement, and finding caps
- [x] Remove the hosted AI provider that depended on Advent's private service
- [x] Keep all AI-assisted workflows available through user-controlled providers
- [x] Set the next application version to 2.0.0
- [x] Complete clean-environment backend and frontend builds on Windows
- [x] Complete smoke tests on Windows and Linux

## Community files

- [x] Add Apache License 2.0
- [x] Add copyright and origin attribution in `NOTICE`
- [x] Add trademark guidance
- [x] Add contribution, support, conduct, and security policies
- [x] Add architecture documentation
- [x] Add issue and pull request templates
- [x] Add continuous integration and dependency update configuration

## Security and rights review

- [x] Scan reachable Git history and prepared source trees with Gitleaks
- [x] Keep the legacy repository private so historical binary assets, logs, and attachments are not disclosed
- [x] Confirm Gitleaks found no credential requiring rotation in the scanned history or release tree
- [x] Receive Advent Cybersecurity authorization for the open-source publication sequence
- [x] Review third-party dependency licenses and generated attribution requirements
- [x] Run dependency vulnerability checks for Python and npm
- [x] Review Tool Runner workflow controls and file-serving authorization
- [x] Enable GitHub private vulnerability reporting, secret scanning, push protection, Dependabot, and code scanning

## Publication

- [x] Create and review the clean public root commit
- [x] Review the complete source diff and omit untested binary artifacts
- [x] Determine that a clean public history is required to exclude legacy tier code, release titles, and binaries
- [x] Approve the clean-public-repository topology in `docs/releases/PUBLICATION_PLAN.md`
- [x] Publish the clean `Advent-Cybersecurity/breachwright` repository
- [x] Publish an annotated `v2.0.0` tag and source-only release
- [x] Update the Advent Cybersecurity product page and remove checkout and subscription paths
- [x] Archive the duplicate private `breachwright-dev` repository after confirming it has no unique branches, tags, releases, or Git tree
- [x] Announce that Advent Cybersecurity created Breachwright and released it fully open source for the community
