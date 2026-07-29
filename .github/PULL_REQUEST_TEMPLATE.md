## Problem

Describe the operator or maintainer problem this change addresses.

## Solution

Explain the approach and important tradeoffs.

## Validation

- [ ] `python -m compileall -q backend/app`
- [ ] `python -m unittest discover -s tests -v`
- [ ] `npm ci` in `frontend`
- [ ] `npm run build` in `frontend`
- [ ] I tested the affected workflow manually.

## Safety and release checks

- [ ] This change contains no credentials, customer data, generated reports, databases, or local environment files.
- [ ] This change does not introduce a paid feature gate, entitlement check, seat limit, engagement limit, or finding limit.
- [ ] User-visible behavior and documentation are updated.
- [ ] I have the right to contribute this code under Apache License 2.0.
