# Breachwright 2.2.0 release checklist

This checklist controls the repeatable-assessment release. A checked item must
have repeatable evidence for the exact candidate commit.

## Product gates

- [x] Scan snapshots classify new, persistent, resolved, and regressed results
- [x] Finding history and risk-first retest queues work end to end
- [x] Built-in templates create the intended methodology checklist
- [x] Web templates create all ten current OWASP Top 10:2025 categories
- [x] API templates create all ten OWASP API Security Top 10 (2023) categories
- [x] Report readiness identifies missing evidence, remediation, pending work,
  unversioned scans, and parser-version concerns
- [x] Nuclei JSONL and SARIF import work with bounded parser inputs
- [x] SARIF finding export is valid SARIF 2.1
- [x] Portable JSON format 1.1 round-trips the documented project records
- [x] Malformed or oversized portable imports fail atomically
- [x] Markdown and DOCX reports generate without an AI provider
- [x] Reports are risk-first, preserve CVSS zero, and do not duplicate attack paths
- [x] Windows, Linux, and WSL instructions contain no account-setup step

## Compatibility and safety gates

- [x] A copied public v2.0.0 SQLite database upgrades with its data intact
- [x] SQLite backup, validation, download, offline restore, and rollback pass
- [x] Uninstall preserves application data unless separately requested
- [x] Candidate archives exclude credentials, databases, logs, and assessment data
- [x] Candidate workflows do not call paid AI services
- [x] Candidate workflows use standard GitHub-hosted runners only
- [x] Candidate workflows retain no binary artifacts before approval
- [x] Public `main`, existing release downloads, and the company site remain unchanged

## Exact-candidate gates

- [ ] Windows source and end-to-end tests pass
- [ ] Linux source and end-to-end tests pass
- [ ] CodeQL passes
- [ ] Windows package, desktop, install, uninstall, and archive tests pass
- [ ] Linux package, desktop, install, uninstall, and archive tests pass
- [ ] Final Windows and Linux archive checksums are reviewed
- [ ] Release notes and public download publication receive deliberate approval

The release must not be published if either supported platform fails or if the
workflow head differs from the reviewed candidate commit.
