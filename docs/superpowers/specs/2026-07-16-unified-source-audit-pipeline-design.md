# Unified Source Audit Pipeline Design

## Goal

All source creation paths use one auditable lifecycle. A candidate can be published only after real parser verification and an evidence-backed review-agent approval. Unavailable review automation leaves the candidate available for manual review; it never bypasses the gate.

## Confirmed policy

- Every create, edit, JSON import, or repair produces a `candidate` source version.
- A single idempotent `source.audit` workflow owns validation and review state.
- The workflow performs real search, table-of-contents, and chapter-content probes before review.
- The review agent must use approved source/page tools and record tool evidence before it can approve.
- Agent rejection, timeout, unavailable provider, or incomplete tool evidence leaves the version as a candidate and creates a manual review item.
- Successful agent review produces `approved_for_publish`; publication remains an explicit administrator action.
- The publish endpoint rejects every version that lacks an approved audit record.

## State model

The source version remains `candidate` until it is explicitly published. Its `payload.source_audit.status` is the sole workflow state:

| Status | Meaning | Publish |
| --- | --- | --- |
| `queued` | Audit task is waiting or running. | Blocked |
| `probing` | Real parser probe is in progress. | Blocked |
| `reviewing` | Evidence is ready and review agent is executing. | Blocked |
| `approved_for_publish` | Probe and review-agent tool evidence passed. | Allowed |
| `manual_review_required` | Probe, agent, provider, or tool evidence did not meet the gate. | Blocked |
| `rejected` | Review agent rejected the candidate. | Blocked |

Each transition records: job id, attempt, timestamps, probe/test-run id, review-agent run id, tool-evidence ids, reason code, and manual-review item id when present. Existing historical `passed`, `failed`, and retry states are migrated or treated conservatively as blocked unless they include the new approval evidence.

## Workflow

1. The common candidate creation service initializes `source_audit` with `queued` and enqueues the idempotent audit job. JSON import creates one queued job per source version; queue limits retain request responsiveness.
2. The worker claims the audit job, changes state to `probing`, runs the full parser chain, and persists a source test run.
3. A passed probe changes state to `reviewing` and invokes the review-agent runtime with a fixed tool allowlist for source/page inspection, rule validation, and review recording.
4. The runtime accepts approval only when the Agent returns an approval decision and recorded evidence covers the probe and required tool calls. It stores `approved_for_publish` on the source version.
5. Any negative or unavailable outcome records a bounded reason code, creates or reuses a `source_audit` review item, and sets `manual_review_required` or `rejected`.
6. The existing explicit publish action checks for `approved_for_publish`, settled test-run data, and a passing real content probe before changing the version to `published`.

## Boundaries

- `SourceAuditWorkflowService` owns status transitions, idempotency, and durable audit records.
- `SourceBuildRuntimeService` remains the page inspection/repair executor, but cannot grant publication eligibility.
- A dedicated review-agent adapter owns model invocation and validates the required tool history; it has no publication capability.
- `SourceRuntimeService.publish_rule_version` is the final policy gate and has no fallback for missing audit data.
- The source build and review queue pages render one serialized audit object rather than inferring state from unrelated jobs.

## Error handling and recovery

- Job leases and idempotency keys prevent duplicate concurrent audits.
- A worker retry resumes from persisted state; it does not repeat a completed agent approval.
- Provider configuration errors, timeouts, unsupported tool calls, and invalid agent output become `manual_review_required`, never a worker crash or a hidden candidate state.
- Publishing returns a machine-readable reason code and Chinese user-facing explanation for every blocked state.

## Acceptance criteria

1. A JSON-imported candidate automatically receives an audit job and cannot publish before approval.
2. A passed full-chain probe invokes the review agent and persists its tool history/evidence.
3. An agent/provider/tool failure creates exactly one manual-review item and leaves the candidate unpublished.
4. An approved candidate can be published and is registered for legacy reading/health flows.
5. A candidate with no audit record, a queued audit, or legacy `passed` data without review evidence cannot publish.
6. API and frontend responses show the current audit phase, reason, and review link.
