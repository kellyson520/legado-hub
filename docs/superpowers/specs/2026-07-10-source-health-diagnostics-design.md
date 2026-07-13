# 2026-07-10 Source Health Diagnostics Design

## Goal

Replace ambiguous `unknown_error` outcomes with durable, actionable diagnostics and add a per-source health detail page. The work covers the existing source-health probe flow, its persisted history, the admin API, the React admin interface, and repeat probes for real sources including `30`, `67`, and `108`.

## Scope

The implementation will:

- Classify failed probe stages as `waf_blocked`, `http_status_error`, `html_instead_of_json`, `parse_empty`, or `unknown_error` only when evidence is insufficient.
- Persist a structured diagnostic summary for every search, toc, and content stage.
- Return a stable single-source detail payload containing the current snapshot and recent probe runs.
- Add `/sources/health/:sourceId` with probe history, request and response previews, route decision, and a chronological failure timeline.
- Re-probe the requested real sources and preserve the resulting evidence in the normal probe history.

The implementation will not add credential automation, store full response bodies, or change the core fetching semantics for a source merely to obtain diagnostics.

## Classification

`SourceProbeService` is the sole producer of stage evidence. Each `StageProbeResult.detail` records available fields such as `http_status`, `http_error`, `response_kind`, `response_preview`, `js_exec_status`, `js_error`, parser outcome, and elapsed time. Response previews are truncated and must exclude request headers, cookies, and authorization values.

`SourceHealthClassifierService` evaluates evidence in this order:

1. Authentication, token, helper, TLS, and connectivity failures retain their existing classifications.
2. WAF detection wins for known challenge content, HTTP `403`/`429`, or connection-reset signatures associated with blocking.
3. Any non-success HTTP status not already classified as WAF or auth is `http_status_error`.
4. A response recognized as HTML where the rule or parser expects structured JSON is `html_instead_of_json`.
5. A successful fetch followed by an empty parser result is `parse_empty`.
6. `unknown_error` is the fallback for a failed stage without decisive evidence.

The health-state rules remain compatible: transport and WAF failures are `blocked`; HTML substitution is `degraded` unless repeated high-confidence evidence proves an upstream change; empty parser output remains `degraded`; `unknown_error` remains `unknown`.

## Data And API Contract

The existing `source_probe_runs` JSON fields remain the persistence boundary. Probe run evidence is normalized at serialization time into a detail shape that includes all three stages and their diagnostic fields. No new table is required.

`GET /api/source-health/book-sources/{source_id}` returns:

- `snapshot`: the current health, three-stage state, failure reason, confidence, route policy and score, and probe timestamps.
- `runs`: recent probe runs ordered newest first, each carrying its probe mode, keyword, stage evidence, classification and route summary.
- `route_decision`: a derived presentation object from the current snapshot, or a `probe_only` default when no snapshot exists.

The list endpoint remains backwards compatible. Its rows gain only optional summary fields needed to link to the detail page.

## Admin Interface

The health list adds an icon-backed detail action that routes to `/sources/health/:sourceId`.

The detail page uses a dense operational layout:

- Header: source identity, current health reason, stage states, and probe/recover controls.
- Route decision: policy, score, skip/deprioritize reason, and next eligible probe time.
- Request preview: method/URL/body summary and the latest safe response summary.
- Probe history: recent runs with timestamps, duration, per-stage state, classification, and expandable diagnostic values.
- Failure timeline: chronological failed or degraded stage events, preserving the causal category and short message.

The page handles empty history and an absent snapshot. It never displays secret headers, cookies, or full response payloads.

## Testing And Real-Source Verification

Backend tests cover classifier precedence, evidence serialization, the single-source detail endpoint, and absence of sensitive data in previews. Frontend tests cover list-to-detail navigation and rendering of all four requested diagnostic categories plus empty-history state.

After local tests pass, the existing source-health probe command will run against sources `30`, `67`, and `108` using the project sample keywords. The resulting classifications and stage evidence will be recorded in the normal database/history and summarized in a checkpoint report. A source-specific upstream failure is a valid result; the verification requirement is that it no longer collapses into an unexplained `unknown_error` when the captured evidence supports a concrete category.
