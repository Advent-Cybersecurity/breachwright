# Breachwright project instructions

## Zero-cost constraint

The incremental development and release infrastructure budget is $0 USD.

- Use only standard GitHub-hosted runners while the repository is public.
- Do not provision paid infrastructure, hosted services, Codespaces, larger
  runners, paid marketplace actions, or paid test services.
- Do not make paid AI API calls during tests.
- Keep temporary workflow artifacts for seven days or less.
- Use local fixtures, mocks, WSL, the existing Windows VM, and standard public
  GitHub-hosted runners.
- Stop before any action that could create a charge and request a separate
  explicit user decision.

## Release constraint

Do not modify the current GitHub release or its downloads until the candidate
passes clean Windows and Linux build, installation, migration, authentication,
core user journey, backup, restore, and report-generation checks.

## Quality requirements

- Preserve existing user data through migrations.
- Add tests for new behavior and important failure paths.
- Apply authorization checks to every new API and file operation.
- Keep AI optional for manual workflows.
- Use no em dashes in reports or public writing.
