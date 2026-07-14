# Source-Build Audit Agent Design

## Context

The source-build Agent can now create a candidate-only Legado rule after bounded inspection and validation. That validation belongs to the build process, however, and does not yet create a durable, independent audit record or a controlled retry loop. A candidate must be exercised as a real reader would use it before a reviewer can publish it: find a book, open the table of contents, and obtain readable chapter content.

## Goal

Automatically audit every source-build candidate after a build run. The audit uses a fresh Legado reader client to run a real search → TOC → content chain, records stage evidence and latency, and permits publication only after a passing audit. A failed audit returns the same candidate to the source-build pipeline for correction. After five failed audit attempts, the candidate is marked failed and a console-visible source-review item is created. No audit path may publish or enable a source.

## Decisions

### Trigger and retry model

Three options were considered:

1. Run audits manually from the operations screen. This is simple but lets untested candidates become publishable.
2. Run audit synchronously inside every build request. This gives immediate feedback but makes the worker responsible for recursive repairs and ties up a worker for all five attempts.
3. Run an audit after each completed source-build job and enqueue a distinct repair build on failure. This keeps jobs bounded, preserves a trace per attempt, and uses the existing job worker for retries.

The implementation uses option 3. A source-build worker completes one build and then invokes the audit service once. The audit service either records a pass, queues one repair build for the same candidate, or terminates at the fifth failure. The next worker cycle performs the repair and invokes audit again.

### Candidate lifecycle

`SourceBuildService.submit()` creates a candidate with `source_audit.status = "pending"`. Until that status is `passed`, source-build candidates are not publishable through the review queue.

| Audit result | Candidate state | Next action |
| --- | --- | --- |
| pass | `candidate`, `source_audit.status = passed` | Human may publish after normal review. |
| fail, attempt 1–4 | `candidate`, `source_audit.status = retry_queued` | Enqueue one same-version `source.build` correction job. |
| fail, attempt 5 | `failed`, `source_audit.status = failed` | Persist a `source_audit_failed` review item; no more automatic work. |

The retry uses the existing deterministic-first source writer. If its policy selects an LLM repair, the existing enabled/provider-configured bounded Agent path may participate; audit itself never receives arbitrary network, code, or publishing tools.

## Audit contract

The audit service accepts a candidate version ID and optional keyword. It only audits candidates with a complete persisted `source_rule`, executes the existing `SourceProbeService` in `full_chain` mode with a newly-created client, and always closes that client.

The passing criteria are intentionally observable and portable:

- Search: status is `ok`, at least one result, and the first title is non-empty.
- TOC: status is `ok`, at least one chapter, and the first chapter title is non-empty.
- Content: status is `ok`, content length is at least 80 characters, and the TOC supplies a chapter title.
- Performance: no stage exceeds 10 seconds and total chain time does not exceed 25 seconds.

For every attempt the report includes the candidate ID, keyword, outcome, attempt/max-attempt numbers, score/grade, total elapsed time, per-stage status/hits/title/content length/elapsed time, and a safe first failure reason. Full HTML, cookies, credentials, and page bodies are not persisted in the audit report.

Each audit creates an existing `SourceTestRun` with trigger `source_audit`, so the candidate's latest validation grade and existing source-health diagnostics remain coherent. The current report is also retained under `payload.source_audit`; its bounded `history` retains all five attempt summaries.

## Failure handling and review

On terminal failure `SourceReviewService.enqueue_audit_failure()` creates a `source_audit_failed` item containing the summary report and failure tags. It is a resolution-only review item: resolving it acknowledges the terminal failure and never enables publication. The candidate status becomes `failed`, so it is absent from ordinary publish candidates but remains visible in the review queue through the source-review entry.

`SourceRuntimeService.resolve_review()` refuses to publish automated source-build candidates unless `payload.source_audit.status` is `passed`. Manual versions that predate the source-build path retain their current review behavior; this is a scoped compatibility rule based on the presence of the `source_audit` marker.

## Console UI

The Operations Source Builds page gains an Audit column that displays status, attempt count, grade, search/TOC/content stage results, total parse time, and the failure reason. The Review Queue exposes the same compact audit summary for source-version and terminal source-review rows. State is conveyed in text, not color alone; its existing semantic table and buttons preserve keyboard and screen-reader access.

## Non-goals

- Do not automatically publish, enable, or replace any source.
- Do not turn audit into a general browser, shell, or arbitrary tool agent.
- Do not introduce provider credentials or claim a live model test before the operator supplies credentials.
- Do not change catalog source-health records; they are a different persistence lifecycle from candidate source versions.

## Test plan

1. A real probe pass records timing/stage evidence, a passing test run, and a publication-eligible audit status.
2. A failed first audit queues exactly one same-version correction job with a unique idempotency key.
3. A fifth failure marks the candidate failed, creates one terminal source-review item, and queues no job.
4. Missing source rules and slow/empty stages fail safely with an audit report instead of exceptions.
5. Source-build scheduler invokes audit only after a completed build and includes its result in the job outcome.
6. Review publishing rejects a pending/failed automated candidate but accepts a passed audit candidate.
7. Operations API and React views render audit state, attempts, latency, and failure evidence.
