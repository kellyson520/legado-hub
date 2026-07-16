# Evidence-First Novel Agent Design

**Status:** Approved design

**Date:** 2026-07-16

## 1. Purpose

Build an evidence-first novel research system on top of LegadoHub. It must let a user use a published book source to search for a work, resolve the work across multiple sources, fetch and align chapters, and ask an Agent about characters, events, chronology, locations, factions, and world rules.

The system must not treat either a model response or an ephemeral web page as a durable fact. Durable knowledge is a versioned claim linked to immutable, locatable chapter evidence. The Agent retrieves that evidence on demand rather than relying on a large, lossy chat context.

Normal use is user-directed and incremental: a user searches, reads, or asks an analysis question for a selected work. Optional background automation only processes new chapters that already belong to an ingested work. It never crawls arbitrary sites, creates sources, or bypasses the source health and browser-verification policies.

## 2. Existing Assets and Boundaries

Reuse the following existing foundations instead of creating parallel stores:

- `canonical_works`, `canonical_chapters`, `source_works`, `source_chapters`, `chapter_alignments`, and `content_variants` remain the canonical content inventory and multi-source content store.
- Published source versions, source health, source routing, and the Legado fetcher remain the only way to reach a book source.
- `agent_runs`, `tool_invocations`, `tool_results`, and `tool_evidence` remain the audit record for Agent activity.
- Existing work-knowledge proposals remain readable during migration. New knowledge APIs use the versioned claim model below and can expose compatible proposal views to existing clients.
- Provider accounts, models, and routes remain the single place where provider credentials and model fallback are stored. Agent settings select a route; they never duplicate provider secrets.

The legacy standalone `services/novel_agent/memory.py` SQLite/file memory is not an authoritative knowledge store. It may remain as a compatibility cache for the legacy agent, but new work analysis uses the application database exclusively.

## 3. Architecture

```text
Published healthy source
  -> source.search / book.resolve / toc.get / chapter.fetch
  -> canonical work + aligned chapter + content variant
  -> evidence span ledger
  -> knowledge claims, events, temporal links, conflicts
  -> evidence-aware Agent tools and answers
```

### 3.1 Content and evidence flow

1. `source.search` uses only enabled, published, healthy sources selected by the existing routing service.
2. `book.resolve` identifies or creates a canonical work using normalized title, author hints, aliases, and source-work mappings. Ambiguous matches remain candidates instead of being silently merged.
3. `toc.get` ingests source chapters and uses the existing alignment service. Low-confidence alignment remains reviewable and is not used for automatic knowledge publication.
4. `chapter.fetch` obtains a source chapter through the existing source reader/fetcher, persists a content variant with the source health and quality metadata, then creates evidence spans from the normalized content.
5. Every durable conclusion points to one or more evidence spans. A span records canonical chapter, content variant, character offsets, excerpt, excerpt hash, content hash, source ID, and creation time.

An evidence span is immutable. A later fetch produces a new content variant and new evidence spans. Claims based on older variants stay traceable and can be re-audited.

### 3.2 Long-context control

An Agent receives only its task goal, a compact work snapshot, relevant published claims, open questions, and selected evidence spans. It does not receive an entire novel or unrestricted prior conversation.

The compact work snapshot contains the current arc summary, key entities, recent events, unresolved conflicts, and chapter coverage. It is derived from published claims and evidence, is versioned, and is never the sole proof for a new claim.

## 4. Persistent Data Model

Add relational application tables; do not require a graph database in the first release.

| Table | Responsibility |
|---|---|
| `evidence_spans` | Immutable, locatable chapter excerpts and content/source hashes. |
| `knowledge_entities` | Characters, factions, locations, objects, and abstract concepts. |
| `knowledge_entity_aliases` | Names, titles, aliases, and unresolved identity candidates. |
| `knowledge_claims` | Versioned candidate/published/superseded/withdrawn assertions. |
| `claim_evidence` | Many-to-many claim-to-evidence references and citation role. |
| `narrative_events` | First-class events with title, summary, chapter range, and status. |
| `event_participants` | Entity roles in an event. |
| `temporal_links` | `before`, `after`, `during`, `overlaps`, or `unknown` relations. |
| `knowledge_conflicts` | Conflicting claims, rationale, affected entities, and resolution state. |
| `agent_analysis_tasks` | Work-scoped, budgeted, resumable analysis tasks. |
| `agent_task_checkpoints` | Compact state after bounded Agent work. |
| `knowledge_adjudications` | Verification and adjudication outcomes, policy version, model route, and reasoning summary. |

`knowledge_claims` has a subject entity, predicate, object entity or scalar value, qualifiers, epistemic class (`explicit`, `inferred`, `speculative`), confidence, temporal scope, lifecycle status, and revision link. It covers ordinary relations, attributes, and world rules without creating one schema per relation type.

Events are separate because they have participants, causal links, and relative chronology. Absolute dates are optional. The first release models relative chronology because many serial novels do not provide a stable calendar.

## 5. Agent Tools and Task Runtime

The tool registry becomes executable for the knowledge Agent and retains a strict allowlist and tenant isolation.

| Tool family | Tools |
|---|---|
| Source reading | `source.search`, `book.resolve`, `toc.get`, `chapter.fetch` |
| Evidence | `evidence.search`, `evidence.get`, `chapter.summary` |
| Knowledge reads | `character.find`, `character.relations`, `plot.find`, `plot.timeline`, `world.find`, `world.rules`, `conflict.detect` |
| Candidate writes | `knowledge.propose`, `knowledge.revise`, `review.request` |

Tools return bounded structured data, explicit resource IDs, source/version metadata, and evidence IDs. Tool results and evidence are immediately recorded in the existing Agent audit tables. An Agent cannot issue arbitrary HTTP requests, read provider secrets, publish a source, or publish knowledge directly.

An analysis task stores work ID, user goal, status (`queued`, `running`, `paused`, `blocked`, `completed`, `failed`), task policy, tool/chapter/token/cost budgets, selected evidence IDs, compact working summary, open questions, and a recovery cursor. The runtime checkpoints after each small tool batch. Budget exhaustion, source errors, conflicting evidence, or provider failure produce a useful paused or blocked task rather than an unbounded retry loop.

## 6. Automated Knowledge Governance

Use independent roles rather than allowing the extractor to approve itself:

```text
Extraction Agent -> Verification Agent -> Adjudication Agent
                                      -> publish | revise | reject | human_review
```

- The extraction Agent proposes a claim with evidence IDs.
- The verification Agent re-reads the cited evidence and verifies offsets, hashes, entity resolution, schema validity, duplicates, and direct conflicts.
- The adjudication Agent independently reads the evidence through `evidence.get`, evaluates the applicable policy, and chooses an outcome. It does not trust the extractor's summary as proof.

Automatic publishing is allowed only when all conditions hold:

1. The cited span and its content hash remain valid.
2. Entities are uniquely resolved and the claim schema is valid.
3. No live published conflict exists.
4. Both verification and adjudication pass under the active policy.
5. The claim is explicit, or it has the policy-required independent evidence for an inferred claim.

Default policy:

- An explicit fact may publish with one verified direct citation and no conflict.
- An inferred fact requires at least two non-overlapping evidence spans.
- Speculative claims cannot auto-publish.
- Identity merges, major identity reversals, source-version contradictions, retcons, and high-impact timeline conflicts always go to `human_review`.

The policy records role, provider route, actual model, prompt version, policy version, verdict, evidence IDs, and concise explanation. A regression audit runs only for claims whose evidence or aligned chapter changed. It can publish a revised claim, mark an older claim superseded, or raise a conflict; it never silently deletes history.

## 7. System Settings Information Architecture

Settings use stable URL paths in the form `/settings/{domain}/{tab}` and a registry-driven back end and front end. A setting domain declares its ID, display metadata, access permission, typed schema, defaults, secret fields, redaction rules, side effects, and audit event. A tab is a child of a domain. New configuration areas register themselves instead of adding isolated pages and hand-written persistence.

Top-level domains:

1. General
2. Security and Access
3. Models and Providers
4. Agents and Automation
5. Sources and Browser
6. Storage and Maintenance
7. Runtime and Observability

`Agents and Automation` has these second-level tabs:

| Tab | Responsibility |
|---|---|
| Overview | Enablement, task queue summary, recent automatic decisions, and exceptions. |
| Roles and Models | Extraction, verification, adjudication, and audit routes with fallback and dry-run test. |
| Automation | User-triggered flow, new-chapter background processing, regression audit, and pause behavior. |
| Evidence and Governance | Publication thresholds, evidence count, conflict policy, and human-review escalation. |
| Budgets and Queue | Per-task chapter/tool/token/cost limits, concurrency, and daily background quota. |
| Audit and Tests | Tool-chain test, decision logs, emergency stop, and resume controls. |

`Models and Providers` remains responsible for provider credentials, models, and generic route definitions. Agent role settings reference those routes and never duplicate credentials.

Every setting save returns the server-normalized complete section and its optimistic-concurrency version. The client only updates from that response, shows a durable saved state and last effective time, redacts secrets as “configured”, and warns on concurrent edits. On small screens, second-level tabs collapse to an accessible selector while preserving the URL and deep-link behavior.

## 8. Delivery Sequence

1. **Settings foundation and policies.** Implement the domain/tab setting registry, URL-based settings shell, Agent governance schemas, role-route references, budget policy, save-state behavior, and emergency pause.
2. **Evidence ingestion and reading tools.** Add evidence spans, connect canonical content ingestion to source search/read flow, and implement bounded source/evidence tools with audit persistence.
3. **Knowledge graph and query tools.** Add entities, claims, events, temporal links, conflicts, proposal/revision APIs, retrieval snapshots, and user-facing work analysis views.
4. **Task orchestration and automatic adjudication.** Add resumable tasks, checkpoints, extractor/verifier/adjudicator roles, policy evaluation, decision logs, and targeted regression audit.
5. **Real-provider acceptance.** With user-provided provider credentials, run source search through published sources, fetch actual chapters, create evidence-backed knowledge, verify automated decisions, and exercise pause/resume and conflict escalation.

Each phase is independently deployable. A missing model route disables only the affected automated role; manual reading, evidence storage, and existing source functions continue to work.

## 9. Acceptance Criteria

- A user can select a healthy published source, search a real work, resolve it, fetch a chapter, and see a persisted evidence span with its source and content hash.
- An Agent answer about a character, event, timeline, or world rule contains citations that resolve to the exact chapter excerpts used.
- A task can be stopped after a checkpoint and resumed without re-fetching already stored evidence or losing open questions.
- A claim that lacks required evidence is rejected before publication.
- A contradiction creates a conflict record and does not overwrite the earlier published claim.
- Safe claims pass extraction, verification, and adjudication and publish automatically under the active policy. High-risk claims enter the human-review queue.
- Agent role configuration, fallback selection, budgets, test result, and emergency stop are reachable from deep-linked second-level settings tabs.
- Saving settings immediately displays the canonical saved value, version, and effective time without revealing secrets.
- Audit records make every automatic decision reproducible from policy version, model route, tool calls, and evidence IDs.

## 10. Non-Goals for the First Release

- No unrestricted web browsing or source creation by a knowledge Agent.
- No autonomous full-site crawl or bulk analysis of every work.
- No dependency on a graph database, vector database, or a new provider credential store.
- No silent automatic merge of character identities or conflicting source versions.
