# Contributing to Breachwright

Thank you for helping improve Breachwright.

## Before opening an issue

- Search existing issues and discussions.
- Use a minimal example that does not contain customer data or credentials.
- For vulnerabilities, follow `SECURITY.md` instead of opening a public issue.

## Development setup

1. Fork and clone the repository.
2. Create a focused branch from `main`.
3. Install the backend requirements in a virtual environment.
4. Run `npm ci` in `frontend`.
5. Make the smallest change that solves the problem.
6. Run the validation commands in the pull request template.

## Pull requests

- Explain the user problem and the chosen approach.
- Add or update tests when behavior changes.
- Update documentation for user-visible changes.
- Keep unrelated formatting or refactors out of the pull request.
- Never commit API keys, assessment data, generated reports, databases, local environment files, or customer information.
- Confirm that your contribution is your original work or that you have the right to submit it.

Unless you state otherwise, contributions intentionally submitted for inclusion in Breachwright are provided under the Apache License 2.0, as described in section 5 of the license.

## Product principles

- All application features must remain available without paid activation or entitlement checks.
- Local-first and self-hosted workflows should remain first-class.
- AI output must stay reviewable by the operator.
- Security-tool execution must be explicit and visible to the user.
- Advent Cybersecurity attribution must remain accurate without implying endorsement of forks.
