# AI trust and evaluation

Breachwright treats every model response as untrusted input. AI features are
optional and do not control manual engagement, evidence, reporting, export,
backup, or restore workflows.

## Finding review workflow

1. Supported parsers normalize uploaded scanner data.
2. Correlation assigns stable Evidence IDs to scanner observations.
3. Large inputs are divided into bounded chunks with an explicit request cap.
4. Scanner and assessment content is enclosed in an untrusted-data boundary.
5. The configured provider returns structured proposals with exact Evidence
   IDs.
6. Schema, record-count, field-size, severity, confidence, and citation checks
   run before any database proposal is created.
7. A proposal with a missing or unknown Evidence ID is discarded.
8. Grounded proposals enter the AI Review Workbench as pending drafts.
9. The operator accepts, edits and accepts, rejects, or bulk reviews drafts.
10. Only an accepted draft becomes a finding and enters cross-engagement
    knowledge data.

Accepted AI-assisted findings retain their evidence references and evidence
confidence. The reviewed proposal history retains the provider and prompt
version. The interface and deterministic reports label accepted findings as
AI-assisted and analyst reviewed.

## Other AI workflows

- Exploitation chains must cite exact accepted finding IDs. Existing chains
  are not removed until a valid grounded replacement is ready.
- Active Directory paths must cite exact object or relationship Evidence IDs,
  and every proposed node must exist in the imported graph.
- Narratives must preserve finding and evidence citation markers.
- AI-assisted reports must preserve every Evidence ID or generation fails.
- Coverage reviews must cite finding, scan, checklist, path, or methodology
  markers.
- Assistant responses receive bounded context with citation markers and show
  the sources supplied to the model.

## Zero-cost regression baseline

The checked-in evaluation suite uses sanitized Nmap, Nessus, Burp Suite, and
Active Directory fixtures plus fake provider responses. It makes no network
requests and no paid model calls.

The release baseline measures:

- precision of at least 0.95
- recall of at least 0.90
- severity accuracy of at least 0.90
- evidence accuracy of 1.00
- grounded output rate of 1.00

Structural tests also cover malformed JSON repair, bounded retries, context
limits, malicious instruction text inside scanner data, stable provenance, and
the accept and reject workflow. Canned results prove that the pipeline and
metrics behave deterministically. They do not claim that every model meets the
quality baseline. Live model comparisons remain manual, opt-in, and disabled
in CI. Local models can be evaluated without API charges.

## Privacy and cost

Scanner analysis is opt-in at the file level. The operator selects up to 50
stored scans with a 50 MB per-file limit and a 250 MB combined limit. A local
preflight reports the selected count, combined size, configured provider, and
redaction state before any provider is initialized. Keeping an upload in an
engagement does not require sending it to the model.

Common API keys, bearer tokens, authorization headers, passwords, private-key
blocks, and JWT-shaped values are redacted locally from AI context by default.
The operator can change this behavior in Settings. Pattern-based redaction
reduces accidental disclosure but cannot identify every secret or sensitive
business value, so operators must still inspect the source material and the
selected provider's terms.

The same local redaction helper is available for deterministic findings CSV
and SARIF exports. CSV export also prefixes formula-shaped cell values so a
spreadsheet application does not interpret finding content as a formula.

Operators decide which provider receives assessment data and must review that
provider's data-handling and pricing terms. Local OpenAI-compatible endpoints
can keep model traffic on operator-controlled systems. Breachwright's project
CI does not call model APIs, provision hosted AI services, or require a paid
test platform.
