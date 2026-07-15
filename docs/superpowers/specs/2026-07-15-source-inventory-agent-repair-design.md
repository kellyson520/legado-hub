# Source Inventory, JSON Upload, and Agent Repair Design

## Goal

Make every user-visible imported, generated, and Agent-repaired source discoverable in one inventory; accept standard Legado JSON files as candidate-only imports; and let the Agent repair a candidate source through a bounded patch-and-validation workflow.

## Confirmed constraints

- A JSON import creates candidate source versions only. It never publishes a source.
- A source can be published only after the existing full validation and audit gates pass.
- Agent repair may inspect bounded source evidence and propose only permitted Legado rule fields. It cannot publish, enable a source, export credentials, or bypass access verification.
- A `verification_wall` is an access state, not a selector/JavaScript defect. It must continue into the existing browser-verification workflow rather than receive a speculative `return` patch.

## Root causes

The current source list is split across two persistence paths. `POST /api/sources/import` creates a candidate in `SourceRuntimeRepository`, while `GET /api/sources/book_sources` reads the legacy source repository. A newly imported or Agent-created candidate can therefore be absent from the user-facing inventory. The current page also has no error state for a failed list request.

The page accepts pasted Legado JSON but has no file reader. The source-build Agent has `rule.propose`, `rule.validate`, and `review.request` tools in background repair runs, but users cannot invoke the same bounded repair workflow from a candidate source page.

The JavaScript runtime already appends a top-level `return` for simple trailing expressions. A `return` recommendation must therefore be based on an explicit `js_result_undefined` diagnostic, not inferred from a failed content fetch. bqgiu-style redirects are classified as `verification_wall` and are not automatically patched.

## Architecture

### Unified source inventory

Add a runtime-backed inventory endpoint that returns published versions plus candidate versions visible to the requesting user. Each row represents a source identity and includes its newest published version, newest visible candidate, audit state, latest validation, and an explicit action link to its candidate editor.

The existing `/sources` page will use this endpoint. It will expose status filters (published, candidate, failed), loading and failure states, and a candidate action for validation or repair. The legacy source CRUD API is left untouched rather than silently mixing two storage models.

### JSON file import

The existing candidate-only `POST /api/sources/import` contract remains the ingestion path. The frontend adds an accept-JSON file control; the browser reads UTF-8 text locally, validates that the root is an object or array, and reuses the same import request as pasted JSON. The result panel reports created, duplicate, and invalid entries, with links to created candidate versions.

The backend continues to sanitize sensitive fields such as cookies, tokens, authorization headers, providers, and internal keys before storage. It accepts standard Legado source objects and arrays.

### Agent repair action

Add an owner-scoped candidate repair endpoint and a `Repair with Agent` action on candidate rows/editor pages. The action starts an Agent run against the selected candidate source version and uses the existing source-page inspection and source-rule tool executor.

The execution contract is:

1. Inspect bounded candidate/probe evidence.
2. Classify the failure as `rule_defect`, `js_result_undefined`, `verification_wall`, or another non-repairable transport condition.
3. For `rule_defect` or an evidenced `js_result_undefined`, propose a patch limited to standard rule fields.
4. Create a new candidate revision, validate search/TOC/content, and request review only after all stages pass.
5. For `verification_wall`, create no speculative patch; preserve the existing manual-browser verification state.

The original candidate is immutable. Users can inspect the repair run and open the resulting candidate revision. No repair action publishes a source.

### JavaScript return diagnosis

Expose a structured JavaScript execution diagnostic in source validation evidence. The diagnostic distinguishes an empty/undefined script result from an HTTP/content verification wall. The repair prompt explicitly states that it may add an explicit top-level `return` only when the diagnostic proves the JavaScript result is undefined and the candidate patch validates full-chain.

## Error handling and security

- Inventory list failures render an actionable error and retry control instead of an indefinite loading state.
- File parsing errors remain local and do not send malformed content to the server.
- Import and repair endpoints require existing source read/write permissions and ownership checks for candidate modifications.
- Agent page tools remain same-origin, bounded, read-only inspection tools; repair writes only a new candidate revision through the approved rule patch path.
- Verification walls retain their classification and never trigger a CAPTCHA solver, proxy, stealth mode, fingerprint change, or cookie extraction.

## Tests

- Backend: candidate-only imports appear in the runtime inventory, access is owner-scoped, duplicate/sensitive fields remain handled, and repair produces a new candidate only after full validation.
- Backend: `verification_wall` results in no return patch; `js_result_undefined` permits a return patch only when validation passes.
- Frontend: inventory renders candidate rows and a list error/retry state; selecting a JSON file invokes the same importer as pasted JSON; repair action states and navigation are covered.
- Regression: existing source import/export, rule-editor validation, source-build audit, and Agent tool allow-list tests remain green.
