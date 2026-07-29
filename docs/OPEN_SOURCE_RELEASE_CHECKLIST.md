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
- [ ] Complete smoke tests on Windows and Linux

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
- [ ] Review legacy binary release assets, workflow logs, and issue attachments before any legacy repository visibility change
- [ ] Rotate any credential found in repository history before publication
- [ ] Confirm Advent Cybersecurity owns or has permission to open-source every source file and bundled visual asset
- [x] Review third-party dependency licenses and generated attribution requirements
- [x] Run dependency vulnerability checks for Python and npm
- [x] Review Tool Runner command construction and file-serving authorization
- [ ] Enable GitHub private vulnerability reporting, secret scanning, push protection, Dependabot, and code scanning

## Publication

- [ ] Commit the release changes to a review branch
- [ ] Review the complete diff and generated build artifacts
- [x] Determine that a clean public history is required to exclude legacy tier code, release titles, and binaries
- [ ] Approve the clean-public-repository topology in `docs/PUBLICATION_PLAN.md`
- [ ] Make `Advent-Cybersecurity/breachwright` public only after the security and rights review passes
- [ ] Publish a signed `v2.0.0` tag and matching source and binary release assets
- [ ] Update the Advent Cybersecurity product page and remove checkout and subscription paths
- [ ] Archive the duplicate private `breachwright-dev` repository after confirming it has no unique history that must be retained
- [ ] Announce that Advent Cybersecurity created Breachwright and released it fully open source for the community
