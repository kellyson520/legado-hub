# Legado Runtime Source Engine Design

> Date: 2026-07-07  
> Workspace: `C:\Users\lihuo\Desktop\legado-hub`  
> Subproject: 2 / 4  
> Runtime target: local Python 3.13 + local SQLite + real source connectivity  
> Git note: this workspace currently has no `.git`; write files directly and use filesystem checkpoints instead of commits.

---

## 1. Goal

Upgrade the current minimal rule-engine shell into a real runtime for source ingestion, testing, repair, regression, deployment, rollback, and diagnostics. The first release covers the source types already present in the repository:

- `book_sources`
- `rss_sources`

The system must perform real `search -> toc -> content` verification for book sources, real feed parsing for RSS sources, keep full test/deployment history, and support fully automatic promotion and rollback under conservative quality gates.

## 2. Confirmed decisions

- Real runtime only; no mock-only milestone.
- All currently supported source families participate in the same runtime model.
- Automatic replacement of published source versions is enabled.
- Quality gate is conservative: no promotion unless all core checks pass, no regression is detected, repeated retests stay stable, and total score is above threshold.
- Parser compatibility target is high Legado-style compatibility, including selector chains, regex/text transforms, and JS sandbox execution.
- Failures must be diagnosable and reversible; automatic rollback is mandatory.

## 3. Scope

### In scope

- Source definition / version / test-run / deployment data model
- Rule parser and executor expansion for CSS, XPath, JSONPath, regex, text pipeline, rule chaining, and JS sandbox
- Real HTTP runtime with retries, headers, charset handling, redirects, timing capture, and response sampling
- Book and RSS adapters with unified diagnostics
- Candidate generation, repair, regression, promotion, quarantine, rollback
- Scheduler-driven health checks for active published versions
- Admin-visible diagnostics APIs consumed by the future control plane
- Real-source regression suite and local smoke commands

### Out of scope

- Inventing brand-new business source types not already represented in the repo
- Browser automation or anti-bot bypass as a first-class subsystem
- Cluster/distributed workers
- Historical migration from pre-refactor runtime data

## 4. Runtime model

The runtime stops treating a source record as a single mutable JSON document. It introduces four first-class objects:

1. `SourceDefinition`: stable identity and metadata (name, host, type, group, enabled state)
2. `SourceVersion`: a versioned rule payload with states `draft / candidate / published / quarantined / rolled_back`
3. `SourceTestRun`: one real execution run containing step-by-step results, response samples, timings, diagnostics, and score
4. `SourceDeployment`: promotion, rollback, or quarantine event linking source definition, versions, quality decision, and actor

This model is shared by book and RSS adapters so the backend and future console can render one operational picture.

## 5. Engine architecture

The source runtime pipeline is:

`fetch -> normalize -> parse -> execute -> postprocess -> validate -> score -> decide`

### Core components

- `http_client.py`: normalized outbound requests with metrics and response sampling
- `parser.py`: rule normalization, shorthand detection, chain tokenization
- `executor.py`: selector execution and result shaping
- `text_pipeline.py`: regex/replace/trim/split/join/substr helpers
- `js_runtime.py`: constrained JavaScript execution with timeout and whitelist helpers
- `source_adapters.py`: book and RSS flow adapters that drive rule execution in business order
- `quality_gate.py`: promotion scoring, regression comparison, rollback triggers
- `scheduler.py`: periodic health verification and automatic quarantine/rollback

## 6. Compatibility target

First release explicitly supports:

- CSS selectors
- XPath
- JSONPath
- Regex extraction / replacement
- String post-processing (`trim`, `split`, `join`, `replace`, `substring`)
- Selector fallback chains and field-level composed rules
- JS sandbox execution with bounded CPU time and no filesystem/network access

Unsupported constructs must fail with structured diagnostics instead of silent empty results.

## 7. Real verification flows

### Book source flow

1. Search using a real keyword
2. Pick at least one concrete book result
3. Resolve detail/toc information
4. Fetch one or more chapters
5. Evaluate completeness, response stability, and parsing quality

### RSS source flow

1. Fetch feed
2. Parse entries
3. Extract required fields
4. Optionally follow entry content if configured
5. Evaluate completeness and parsing quality

Each step records request summary, response summary, field hits, missing fields, execution diagnostics, elapsed time, and pass/fail status.

## 8. Automatic generation, repair, deployment, rollback

- `generate`: produce a new `candidate` version from URL/sample/site analysis
- `repair`: attempt syntax, selector, or fallback repairs against an existing candidate/published version
- `regression`: compare candidate vs current published version over a configured sample run-set
- `deploy`: automatically promote a candidate to `published` when quality gate passes
- `quarantine`: mark a published version unsafe after repeated runtime failures
- `rollback`: automatically restore the last healthy published version after quarantine

Promotion requires all of the following:

- core flow succeeds (`search/toc/content` for book, required feed flow for RSS)
- required fields are present
- candidate is not worse than the current published version
- repeated retests stay stable
- score and grade meet configured thresholds

## 9. API surface

The backend should expose or extend these endpoints under the existing authenticated main API:

- `GET /api/sources/book_sources`
- `GET /api/sources/rss_sources`
- `GET /api/sources/{type}/{source_id}/versions`
- `POST /api/engine/generate`
- `POST /api/engine/evaluate`
- `POST /api/engine/repair`
- `POST /api/engine/test`
- `POST /api/engine/regression`
- `POST /api/engine/deploy`
- `GET /api/engine/runs`
- `GET /api/engine/deployments`
- `GET /api/engine/diagnostics/{run_id}`

`generate`, `repair`, `regression`, and `deploy` all write durable records. `test` may be on-demand but still persists the run for operations review.

## 10. Persistence and observability

SQLite schema additions should include, at minimum:

- `source_definitions`
- `source_versions`
- `source_test_runs`
- `source_run_steps`
- `source_deployments`
- `source_health_events`

The runtime keeps trimmed response samples, not full unbounded payloads. Diagnostic output remains structured so the future console can render timelines, diffs, and failure reason trees.

## 11. Testing strategy

- Unit tests for parser, executor, text pipeline, JS sandbox, quality gate
- Adapter integration tests for book and RSS flows
- Repository tests for version/run/deployment persistence
- API tests for generate/repair/regression/deploy endpoints
- Real-source smoke suite against a locally maintained pool of live sources

## 12. Risks and constraints

- Real sites are unstable; the system must prefer diagnosability and rollback over apparent success rate.
- JS compatibility can grow without bound; the first release needs a documented supported subset and explicit diagnostics for unsupported constructs.
- Full automatic replacement is inherently risky; deployment history and rollback must be implemented before automation is enabled.
- Local Python 3.13 execution and SQLite durability remain mandatory constraints.

## 13. Acceptance criteria

This subproject is complete when:

- Book and RSS sources both run through real verification flows
- High-compatibility rule execution is available for the supported subset
- JS sandbox executes bounded scripts with structured diagnostics
- Generate / repair / regression / deploy flows persist history
- Published versions can be automatically quarantined and rolled back
- Authenticated APIs expose runs, deployments, and diagnostics for the future control plane
- Local verification succeeds on Python 3.13 with SQLite
