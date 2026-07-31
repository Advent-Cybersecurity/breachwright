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
- Exploitation-chain input is capped at 200 findings with bounded free-text
  fields, and a model response can contain at most 25 chains. Active Directory
  analysis accepts at most 100 returned paths. Larger results fail without
  replacing previously reviewed records.
- Active Directory paths must cite exact object or relationship Evidence IDs,
  and every proposed node must exist in the imported graph.
- Narratives must preserve finding and evidence citation markers.
- AI-assisted reports must preserve every Evidence ID or generation fails.
- Before AI report generation, a provider-free preflight shows the bounded
  context size, provider, local redaction state, and readiness. Disabling
  redaction requires an additional confirmation before report context is sent.
- Coverage reviews must cite finding, scan, checklist, path, or methodology
  markers.
- Coverage review rejects more than 500 findings, 1,000 checklist items, 1,000
  scan records, or 100 attack paths before detailed records are loaded or a
  provider is initialized. Narrative generation similarly rejects more than
  500 findings or 100 attack paths before provider use.
- Assistant responses receive bounded context with citation markers and show
  the sources supplied to the model.
- Assistant requests reject missing engagement scopes before provider
  initialization. Citation IDs are accepted only when their markers survived
  the final context bound, and the interface shows the active provider and
  redaction state before a message is sent.
- Assistant finding fields and evidence-reference lists are bounded before the
  final prompt is assembled. Scan excerpts use bounded binary reads on a worker
  thread, so a large stored scan is not loaded in full or read on the request
  loop.

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

When **Analyze with AI** is selected for a completed Tool Runner job,
Breachwright copies that job's structured result into Scans and submits only
that scan ID. Other scans in the engagement are not included implicitly.

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

Every generative action shows the active provider and local redaction state
before it can start. External-provider actions include a cost notice. If the
local privacy-settings check cannot complete, the action stays disabled with a
retry control. When redaction is intentionally disabled, Breachwright requires
an additional confirmation before sending context.

Provider initialization and request failures are handled at the workflow
boundary. The interface receives a stable recovery message, while logs record
only the exception type rather than raw provider response text that could
contain assessment data.
