# Dependency security review

## Current release status

- The pinned Python dependency set has no known vulnerabilities in `pip-audit`.
- The npm build-tool advisories were resolved through non-breaking lockfile updates.
- The production web dependency audit reports one upstream React Router advisory,
  [GHSA-qwww-vcr4-c8h2](https://github.com/advisories/GHSA-qwww-vcr4-c8h2).

## React Router advisory assessment

The remaining advisory affects React Router's React Server Components mode.
Breachwright is a Vite-built browser application that uses `BrowserRouter`,
`Routes`, and client-side navigation. It does not use React Server Components,
React Router framework mode, server actions, or action request processing.
The vulnerable execution path is therefore not present in Breachwright.

React Router DOM is pinned to 7.18.2 because older releases carry additional
browser, redirect, denial-of-service, and server-rendering advisories. React
Router 8.3.0 clears the remaining advisory, but its published package requires
React 19.2.7 or newer and Node.js 22.22.0 or newer. Moving to that release is a
coordinated runtime migration, not a safe patch-level dependency change for the
current React 18 and Node 18 source-install baseline.

The CI audit allows only the RSC advisory above and fails if any other
production npm advisory appears. Remove the exception during the planned React
19, Node 22, Vite 7, and React Router 8 compatibility migration.

## Release checks

Run these checks for every dependency update:

```bash
python -m pip_audit -r backend/requirements.txt
cd frontend
npm ci
npm run audit:release
npm run build
```

Review [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) whenever package
versions or the resolved dependency graph changes.
