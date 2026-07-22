# Novel Adaptive Memory Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fast, evidence-first novel knowledge pipeline that extracts characters, items, events and state changes locally, uses Agent only for bounded ambiguity, and exposes the resulting memory through reliable retrieval tools and a polished chat UI.

**Architecture:** Keep `NovelIndexService`, `NovelEntity`, `NovelRelationship`, `NovelEvent`, `NovelStateChange`, `BM25Index`, `RAGRetriever`, `VectorStore`, `NovelAgentAppService` and the existing analysis pipeline as the application boundaries. Add a local candidate/evidence layer, chapter extraction snapshots for idempotent aggregation, typed memory records, an optional adjudicator gateway, and a bounded learning profile. The local SQLite schema remains the source of truth; vector backends are incremental projections.

**Tech Stack:** Python 3, asyncio, aiosqlite/SQLAlchemy, pytest, SQLite, existing Provider/embedding routes, React 18, TypeScript, Vitest, `react-markdown`, `remark-gfm`, `rehype-sanitize`, Tailwind CSS.

---

## Task 1: Lock down local extraction regressions

**Files:**
- Create: `backend/tests/test_novel_auto_extractor.py`
- Modify: `backend/tests/test_novel_index_service.py`
- Test command: `backend/.venv/bin/pytest -q backend/tests/test_novel_auto_extractor.py backend/tests/test_novel_index_service.py` from repository root, or `pytest -q tests/test_novel_auto_extractor.py tests/test_novel_index_service.py` from `backend/`.

- [ ] **Step 1: Write the failing extractor tests**

Add tests that call the public compatibility import `app.services.novel_understanding.auto_extractor.AutoExtractor`:

~~~python
def test_local_extractor_rejects_sentence_fragments_and_keeps_evidence_backed_name():
    from app.domain.entities.novel import EntityType
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    entities, relationships = AutoExtractor().extract_from_chapter(
        8, 0, "序章", "江轩赶到门前。江轩很谨慎，江轩说：‘先等等。’周宁看向江轩。"
    )

    names = {item.name for item in entities if item.entity_type == EntityType.CHARACTER}
    assert "江轩" in names
    assert "江轩很" not in names
    assert "江轩赶" not in names
    assert "周围的" not in names


def test_local_extractor_recognizes_an_item_from_name_and_action_context():
    from app.domain.entities.novel import EntityType
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    entities, _ = AutoExtractor().extract_from_chapter(
        8, 1, "得剑", "江轩从石匣中取出玄天剑，剑身泛起寒光。他握住玄天剑冲向黑衣人。"
    )

    item = next(entity for entity in entities if entity.name == "玄天剑")
    assert item.entity_type == EntityType.ITEM
    assert item.appearance_count == 2
    assert item.attributes["evidence"]


def test_local_extractor_does_not_create_cartesian_relationships():
    from app.services.novel_understanding.auto_extractor import AutoExtractor

    _, relationships = AutoExtractor().extract_from_chapter(
        8, 1, "会面", "江轩与周宁并肩作战。赵明在远处观望。"
    )

    pairs = {(item.source_entity, item.target_entity) for item in relationships}
    assert ("江轩", "周宁") in pairs or ("周宁", "江轩") in pairs
    assert ("江轩", "赵明") not in pairs
    assert all(getattr(item, "evidence", []) for item in relationships)
~~~

Add an index fixture with a chapter whose `canonical_num` is exactly `0` and assert it is processed rather than silently returned as empty.

- [ ] **Step 2: Run the focused tests and verify the expected failures**

Run:

~~~bash
cd /tmp/legado-hub-main-merge/backend
pytest -q tests/test_novel_auto_extractor.py tests/test_novel_index_service.py
~~~

Expected: the new tests fail because the current substring regex emits fragments, does not classify items, creates broad relationship pairs, and `_chapters()` starts at `1`.

- [ ] **Step 3: Commit the red tests**

~~~bash
cd /tmp/legado-hub-main-merge
git add backend/tests/test_novel_auto_extractor.py backend/tests/test_novel_index_service.py
git commit -m "test: lock down novel extraction regressions"
~~~

## Task 2: Implement the evidence-first local candidate extractor

**Files:**
- Create: `backend/app/application/services/novel_understanding/candidate_extractor.py`
- Modify: `backend/app/application/services/novel_understanding/auto_extractor.py`
- Test: `backend/tests/test_novel_auto_extractor.py`

- [ ] **Step 1: Define the candidate contract**

Create immutable dataclasses with the following fields:

~~~python
@dataclass(frozen=True)
class CandidateEvidence:
    chapter_id: int
    chapter_num: int
    start_offset: int
    end_offset: int
    text: str
    features: tuple[str, ...] = ()


@dataclass
class LocalCandidate:
    name: str
    entity_type: EntityType
    score: float
    mentions: int
    evidence: list[CandidateEvidence]
    aliases: list[str] = field(default_factory=list)
    subtype: str = ""
    status: str = "confirmed"
~~~

Use one compiled sentence/paragraph scanner per chapter. Candidate generation must cover explicit naming phrases, dialogue/action attribution, title/称谓 neighbors, repeated references, and item actions such as 获得/取出/使用/佩戴/赠予/损坏. Common surnames are only a positive feature.

- [ ] **Step 2: Add deterministic filters and bounded scoring**

Implement in `candidate_extractor.py`:

- normalization that strips surrounding quotes and titles while retaining the raw mention as an alias;
- a negative lexicon for function words, verb fragments, adjective fragments, body parts and generic relationship words;
- evidence-aware `score_candidate()` with bounded output `[0.0, 1.0]`;
- item subtype detection stored as `attributes["subtype"]` rather than a second item schema;
- conservative alias merging only for explicit `又称/原名/自称/改名` patterns or stable cross-sentence evidence;
- `extract_relationships()` that accepts only two resolved candidates within one sentence, adjacent sentences or one paragraph and attaches evidence to every result.

Do not call a provider, embedding service or Agent from this module.

- [ ] **Step 3: Keep `AutoExtractor` as the compatibility facade**

Refactor `AutoExtractor.extract_from_chapter()` to delegate to the new candidate extractor and continue returning `(entities, relationships)` for existing callers. Add `extract_with_evidence()` for the index service. Populate `NovelEntity.attributes` with:

~~~python
{
    "extraction_status": candidate.status,
    "confidence": candidate.score,
    "subtype": candidate.subtype,
    "evidence": [asdict(item) for item in candidate.evidence],
    "mention_count": candidate.mentions,
}
~~~

Remove the generic relationship fallbacks that pair every active character and the adjective-only lover rules. The `backend/app/services/novel_understanding/` compatibility wrappers remain unchanged.

- [ ] **Step 4: Run the focused tests and commit the green local extractor**

~~~bash
cd /tmp/legado-hub-main-merge/backend
pytest -q tests/test_novel_auto_extractor.py
cd ..
git add backend/app/application/services/novel_understanding/candidate_extractor.py backend/app/application/services/novel_understanding/auto_extractor.py backend/tests/test_novel_auto_extractor.py
git commit -m "feat: improve evidence-first novel extraction"
~~~

Expected: the focused extractor tests pass without any model/provider calls.

## Task 3: Persist chapter snapshots, evidence and aggregate knowledge safely

**Files:**
- Modify: `backend/app/domain/entities/novel.py`
- Modify: `backend/app/domain/entities/novel_runtime.py`
- Modify: `backend/app/domain/repositories/novel_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py`
- Modify: `backend/app/database_migrations/novel_schema.sql`
- Modify: `backend/app/infrastructure/persistence/sqlite/novel_db_migrator.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Modify: `backend/tests/test_novel_repo.py`
- Modify: `backend/tests/test_novel_index_service.py`

- [ ] **Step 1: Write persistence tests before changing the schema**

Add tests for:

~~~python
async def test_evidence_round_trips_for_relationship_event_and_state_change(repo):
    from app.domain.entities.novel import EventType, NovelBook, NovelEvent, NovelRelationship, NovelStateChange, RelationType, StateField

    book = await repo.save_book(NovelBook(book_url="https://evidence.test", book_name="证据书"))
    evidence = [{"chapter_id": 0, "start_offset": 2, "end_offset": 12, "text": "正文证据"}]
    relationship = NovelRelationship(book_id=book.id, source_entity="江轩", target_entity="周宁", relation_type=RelationType.ALLY, description="并肩作战", evidence=evidence)
    event = NovelEvent(book_id=book.id, chapter_id=0, chapter_num=0, event_type=EventType.BATTLE, description="并肩作战", participants=["江轩", "周宁"], evidence=evidence)
    state = NovelStateChange(book_id=book.id, entity_name="玄天剑", chapter_id=0, chapter_num=0, field_name=StateField.POSSESSION, before_value="", after_value="江轩", trigger_event="获得", evidence=evidence)
    await repo.save_relationship("user:1", relationship)
    await repo.save_event("user:1", event)
    await repo.save_state_change("user:1", state)
    assert (await repo.get_relationships("user:1", book.id, limit=10))[0].evidence == evidence
    assert (await repo.get_events("user:1", book.id, limit=10))[0].evidence == evidence
    assert (await repo.get_state_changes("user:1", book.id, limit=10))[0].evidence == evidence


async def test_rebuilding_book_knowledge_from_snapshots_updates_counts(repo):
    from app.domain.entities.novel import NovelBook

    book = await repo.save_book(NovelBook(book_url="https://snapshot.test", book_name="快照书"))
    first = {"chapter_id": 1, "chapter_num": 1, "entities": [{"name": "江轩", "entity_type": "character", "appearance_count": 2}], "relationships": [], "events": [], "state_changes": []}
    second = {"chapter_id": 2, "chapter_num": 2, "entities": [{"name": "玄天剑", "entity_type": "item", "appearance_count": 1}], "relationships": [], "events": [], "state_changes": []}
    await repo.replace_book_knowledge("user:1", book.id, [first, second])
    initial = await repo.get_book_by_id("user:1", book.id)
    assert initial.character_count == 1
    assert initial.entity_count == 2
    await repo.replace_book_knowledge("user:1", book.id, [second])
    updated = await repo.get_book_by_id("user:1", book.id)
    assert updated.character_count == 0
    assert updated.entity_count == 1
~~~

The tests must use the existing in-memory novel schema fixture and verify owner-scope isolation.

- [ ] **Step 2: Add evidence and snapshot fields**

Add `evidence: list[dict[str, Any]]` to `NovelRelationship`, `NovelEvent`, and `NovelStateChange`. Add `extraction_payload: dict[str, Any]` to `NovelIndexState`. Extend the standalone SQL and migrator with JSON text columns, preserving existing databases through additive `ALTER TABLE` checks. Mirror the fields in SQLAlchemy models.

- [ ] **Step 3: Add repository contracts and transactional rebuild**

Add these methods to `NovelRepository` and `SqliteNovelRepository`:

~~~python
async def list_index_states(self, owner_scope: str, book_id: int) -> list[NovelIndexState]: ...
async def replace_book_knowledge(self, owner_scope: str, book_id: int, snapshots: list[dict[str, Any]]) -> dict[str, int]: ...
async def update_book_statistics(self, owner_scope: str, book_id: int, counts: dict[str, int]) -> bool: ...
~~~

`replace_book_knowledge()` must run in one transaction: delete extraction-owned rows for the book, deserialize all successful chapter snapshots, merge entities by canonical name, deduplicate evidence-backed relationships/events/state changes, insert the merged rows, count by type, and update `novels.character_count/entity_count/event_count/relationship_count`. A chapter re-run replaces its snapshot rather than incrementing old totals.

Update all row converters and SQL column lists in the same change so added evidence/payload columns cannot shift indexes silently.

- [ ] **Step 4: Run repository tests and commit**

~~~bash
cd /tmp/legado-hub-main-merge/backend
pytest -q tests/test_novel_repo.py tests/test_novel_index_service.py
cd ..
git add backend/app/domain/entities/novel.py backend/app/domain/entities/novel_runtime.py backend/app/domain/repositories/novel_repo.py backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py backend/app/database_migrations/novel_schema.sql backend/app/infrastructure/persistence/sqlite/novel_db_migrator.py backend/app/infrastructure/persistence/sqlite/schema.py backend/tests/test_novel_repo.py backend/tests/test_novel_index_service.py
git commit -m "feat: persist novel extraction evidence snapshots"
~~~

## Task 4: Make indexing include unparsed chapters and rebuild deterministically

**Files:**
- Modify: `backend/app/application/services/novel_understanding/index_service.py`
- Modify: `backend/app/tasks/novel_index_worker.py`
- Modify: `backend/app/tasks/scheduler.py`
- Modify: `backend/app/application/services/novel_ingestion_service.py` only where the existing upload completion path creates index tasks
- Test: `backend/tests/test_novel_index_service.py`
- Test: `backend/tests/test_novel_index_worker.py`
- Test: `backend/tests/test_novel_ingestion_service.py`

- [ ] **Step 1: Write failing tests for chapter zero and automatic repair**

Add tests that create a book with one `canonical_num=0` chapter and assert `IndexResult.processed_chapters == 1`. Add a worker test where the runtime task list is empty but `NovelRepository.list_books()` returns a book with chapters and no completed index state; assert the worker creates and processes one repair task. Add a second run assertion that no duplicate task is created.

- [ ] **Step 2: Fix chapter selection and snapshot persistence**

Change `NovelIndexService._chapters()` to use `start_num=0` when `from_chapter` is empty and pass a stable order that includes zero. After local and structured extraction are validated, serialize the chapter result into `NovelIndexState.extraction_payload`, save it, and call `replace_book_knowledge()` from all successful snapshots. Preserve deterministic local entities when structured validation fails; mark only the structured portion failed.

Increment `knowledge_version` from `v1` to `v2-local-evidence` so existing stale snapshots are reprocessed once. Keep `_can_skip()` based on content hash, knowledge version, embedding model and dimension.

- [ ] **Step 3: Add missing-task discovery to the worker**

Before consuming queued tasks, query books in the requested owner scope and persist one queued repair task for a book when it has chapters but no completed state, a failed state, a version mismatch, or zero statistics. Deduplicate by `(owner_scope, book_id)` against queued/running tasks before inserting. Respect the existing `limit`, preserve task status transitions, and continue after a single book failure.

- [ ] **Step 4: Run worker and ingestion tests and commit**

~~~bash
cd /tmp/legado-hub-main-merge/backend
pytest -q tests/test_novel_index_service.py tests/test_novel_index_worker.py tests/test_novel_ingestion_service.py
cd ..
git add backend/app/application/services/novel_understanding/index_service.py backend/app/tasks/novel_index_worker.py backend/app/tasks/scheduler.py backend/app/application/services/novel_ingestion_service.py backend/tests/test_novel_index_service.py backend/tests/test_novel_index_worker.py backend/tests/test_novel_ingestion_service.py
git commit -m "fix: recover and index incomplete novel books"
~~~

## Task 5: Add item/world memory cards and incremental vector projection

**Files:**
- Modify: `backend/app/domain/repositories/vector_store.py`
- Modify: `backend/app/infrastructure/vectorstores/sqlite.py`
- Modify: `backend/app/infrastructure/vectorstores/qdrant.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Modify: `backend/app/database_migrations/novel_schema.sql`
- Create: `backend/app/application/services/novel_understanding/memory_cards.py`
- Modify: `backend/app/application/services/novel_understanding/index_service.py`
- Modify: `backend/app/application/services/novel_understanding/retriever.py`
- Test: `backend/tests/test_vector_store.py`
- Create: `backend/tests/test_novel_memory_cards.py`

- [ ] **Step 1: Write the vector identity regression test**

Extend the SQLite vector fixture to upsert two records anchored to the same chapter with distinct `record_key` values (`chapter:1` and `entity:item:玄天剑`). Assert both survive the upsert and are returned by semantic search with their memory metadata.

- [ ] **Step 2: Extend the vector record identity without breaking callers**

Add `record_key: str = ""` after the existing `score` field in `VectorRecord`. Existing positional constructors remain valid. Use `chapter:{chapter_id}` when empty. Change SQLite and Qdrant point identities to use the stable record key and include it in payload. Add an additive SQLite migration that creates the new keyed table/index for old installations while preserving existing chapter records.

- [ ] **Step 3: Build compact memory cards**

Create `memory_cards.py` with pure functions named `entity_memory_card(entity, evidence_limit=3)`, `event_memory_card(event, evidence_limit=2)`, and `state_memory_card(state, evidence_limit=2)`. Each function returns a bounded string containing type, name, attributes, chapter range, confidence and selected evidence.

Cards must include name/type, aliases, attributes, chapter range, confidence and bounded evidence text. Use content hashes to avoid re-embedding unchanged cards. Index chapter text plus memory cards through the existing `EmbeddingAdapter.embed_batch()` and keep local BM25 text aligned with the same cards.

- [ ] **Step 4: Make retrieval return memory types and citations**

Update `RAGRetriever` to map vector payloads with `memory_type` values `chapter`, `entity`, `event`, and `state` to `RetrievalResult.item_type`, preserve the anchor chapter and return evidence/citation metadata. Keep BM25 and KG retrieval functional when embeddings are disabled.

- [ ] **Step 5: Run vector/memory tests and commit**

~~~bash
cd /tmp/legado-hub-main-merge/backend
pytest -q tests/test_vector_store.py tests/test_novel_memory_cards.py tests/test_rag_retriever.py
cd ..
git add backend/app/domain/repositories/vector_store.py backend/app/infrastructure/vectorstores/sqlite.py backend/app/infrastructure/vectorstores/qdrant.py backend/app/infrastructure/persistence/sqlite/schema.py backend/app/database_migrations/novel_schema.sql backend/app/application/services/novel_understanding/memory_cards.py backend/app/application/services/novel_understanding/index_service.py backend/app/application/services/novel_understanding/retriever.py backend/tests/test_vector_store.py backend/tests/test_novel_memory_cards.py backend/tests/test_rag_retriever.py
git commit -m "feat: index novel entity and event memories"
~~~

## Task 6: Add bounded Agent adjudication and novel memory tools

**Files:**
- Create: `backend/app/application/services/novel_understanding/adjudicator.py`
- Modify: `backend/app/application/services/novel_understanding/index_service.py`
- Modify: `backend/app/application/services/novel_analysis_prompts.py`
- Modify: `backend/app/application/services/novel_agent_app_service.py`
- Modify: `backend/app/domain/repositories/novel_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py`
- Modify: `backend/app/database_migrations/novel_schema.sql`
- Modify: `backend/app/infrastructure/persistence/sqlite/novel_db_migrator.py`
- Create: `backend/tests/test_novel_adjudicator.py`
- Modify: `backend/tests/test_novel_agent_app_service.py`

- [ ] **Step 1: Write tests for the adjudicator boundary**

Cover three behaviors: a high-confidence candidate returns a local acceptance without a provider call; an ambiguous batch produces exactly one provider request containing only bounded evidence; and provider failure returns pending decisions while the index result still succeeds. The fake provider records calls, and the test rejects an Agent response containing an evidence ID not present in the request.

The fake provider must record calls and assert that payloads contain only candidate evidence, never full chapter text beyond the configured evidence window. The test must also reject an Agent response containing an evidence ID not present in the request.

- [ ] **Step 2: Implement the optional adjudicator gateway**

Define an async `adjudicate(owner_scope, book_id, candidates)` interface returning one validated decision per candidate.

The implementation batches only candidates with status `candidate` or `conflict`, caps each request, routes through the existing `novel_adjudicate` provider group, requests strict JSON, validates verdicts `accept/reject/merge/split/pending`, and requires evidence IDs from the supplied set. A cache key uses owner, book, content hash, candidate hash, knowledge version and prompt version. Any exception returns `pending` decisions and does not raise out of chapter indexing.

- [ ] **Step 3: Persist pending adjudication records**

Add a small `novel_adjudication_candidates` table with owner scope, book/chapter IDs, candidate payload, evidence payload, status, decision, attempts, content hash, and timestamps. Add repository methods to upsert pending candidates and list/update decisions. The table is a queue, not a second knowledge graph.

- [ ] **Step 4: Expose read-only tools with evidence**

Extend `_TOOL_CATEGORIES`, `_tool_description()`, `_tool_parameters()`, and `_execute_novel_tool()` with:

~~~text
novel.search_memory
novel.get_entity_profile
novel.get_mentions
novel.get_relations
novel.timeline
novel.get_item_state
novel.compare_entities
novel.get_chapter_evidence
novel.index_status
~~~

Every result must enforce selected book ownership and include `chapter_id/chapter_num`, `evidence`, `confidence`, and `knowledge_version` where applicable. Do not expose rebuild or arbitrary write tools through normal chat.

- [ ] **Step 5: Run Agent tests and commit**

~~~bash
cd /tmp/legado-hub-main-merge/backend
pytest -q tests/test_novel_adjudicator.py tests/test_novel_agent_app_service.py tests/test_api_novel_agent.py
cd ..
git add backend/app/application/services/novel_understanding/adjudicator.py backend/app/application/services/novel_understanding/index_service.py backend/app/application/services/novel_analysis_prompts.py backend/app/application/services/novel_agent_app_service.py backend/app/domain/repositories/novel_repo.py backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py backend/app/database_migrations/novel_schema.sql backend/app/infrastructure/persistence/sqlite/novel_db_migrator.py backend/tests/test_novel_adjudicator.py backend/tests/test_novel_agent_app_service.py backend/tests/test_api_novel_agent.py
git commit -m "feat: add bounded novel Agent adjudication tools"
~~~

## Task 7: Add versioned, conservative local learning

**Files:**
- Create: `backend/app/application/services/novel_understanding/adaptive_learning.py`
- Modify: `backend/app/application/services/novel_understanding/auto_extractor.py`
- Modify: `backend/app/domain/repositories/novel_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py`
- Modify: `backend/tests/test_novel_auto_extractor.py`
- Create: `backend/tests/test_novel_adaptive_learning.py`

- [ ] **Step 1: Write the learning safety tests**

Test that repeated evidence-backed confirmations add a book-scoped alias/pattern, repeated evidence-backed rejections add a negative term, ordinary free-form chat text is ignored, weights stay within configured bounds, and a failed update leaves the previous profile intact.

- [ ] **Step 2: Reuse `EvolutionFeedback` and `EvolutionRule` storage**

Implement `AdaptiveLearningService` over the existing evolution tables. Store book-scoped rule types `novel_alias`, `novel_negative_term`, and `novel_feature_weight` in the existing `condition` JSON field. Require repeated independent evidence or an explicit structured correction before activation; clamp weights and keep `active`, `success_count`, `failure_count`, and source feedback IDs.

- [ ] **Step 3: Apply the profile to local extraction**

Load the active book profile once per indexing run and pass it into `CandidateExtractor`. Apply only aliases, negative terms and bounded feature multipliers. Never modify Python source, arbitrary prompts or other books' profiles. Record the algorithm/profile version in entity attributes and index state.

- [ ] **Step 4: Run learning tests and commit**

~~~bash
cd /tmp/legado-hub-main-merge/backend
pytest -q tests/test_novel_adaptive_learning.py tests/test_novel_auto_extractor.py
cd ..
git add backend/app/application/services/novel_understanding/adaptive_learning.py backend/app/application/services/novel_understanding/auto_extractor.py backend/app/domain/repositories/novel_repo.py backend/app/infrastructure/persistence/sqlite/novel_repo_impl.py backend/tests/test_novel_adaptive_learning.py backend/tests/test_novel_auto_extractor.py
git commit -m "feat: add conservative novel extraction learning"
~~~

## Task 8: Normalize UTC serialization and render safe GFM chat output

**Files:**
- Create: `backend/app/core/time.py`
- Modify: `backend/app/domain/entities/ai_conversation.py`
- Modify: `backend/app/application/services/novel_agent_app_service.py`
- Modify: `backend/app/application/services/ai_workspace_service.py`
- Create: `backend/tests/test_ai_time_serialization.py`
- Modify: `frontend/package.json`
- Create: `frontend/src/components/ai/MarkdownMessage.tsx`
- Create: `frontend/src/components/ai/ToolResultRenderer.tsx`
- Create: `frontend/src/lib/time.ts`
- Modify: `frontend/src/features/ai/AIWorkspacePage.tsx`
- Modify: `frontend/src/features/ai/AIWorkspacePage.test.tsx`
- Create: `frontend/src/lib/time.test.ts`

- [ ] **Step 1: Write backend and frontend red tests**

Backend tests must assert a naive historical datetime serializes with a `Z` suffix as UTC and an aware datetime preserves its instant. Frontend tests must assert a UTC timestamp is rendered with a full local time and a relative label, and a legacy `YYYY-MM-DD HH:mm:ss` value is treated as UTC rather than local wall-clock time. Add a Markdown test fixture containing a GFM table, blockquote and fenced code.

- [ ] **Step 2: Implement one UTC normalization helper**

Create `ensure_utc()` and `to_utc_iso()` in `backend/app/core/time.py`. Use them in both AI serialization services and change AI conversation default factories to `datetime.now(timezone.utc)`. Keep database reads compatible with naive legacy values by treating them as UTC at the API boundary.

- [ ] **Step 3: Add the Markdown renderer and typed tool-result renderer**

Install the existing-compatible packages with:

~~~bash
cd /tmp/legado-hub-main-merge/frontend
npm install react-markdown remark-gfm rehype-sanitize
~~~

`MarkdownMessage` must use `remark-gfm` and `rehype-sanitize`, render links with safe protocols, and apply the existing typography/table classes. `ToolResultRenderer` must render arrays of objects as the existing `DataTable` pattern, scalar objects as readable key/value rows, and fallback JSON in a bounded code block. No `dangerouslySetInnerHTML` is permitted.

- [ ] **Step 4: Replace the plain paragraph and ad-hoc time formatter**

Update `AIWorkspacePage.tsx` to use the two components, preserve authorization/retry behavior, show role/status styling, and use a shared `formatRelativeTime()` plus a `<time dateTime>` full-time tooltip. Keep tool result details collapsible and prevent unbounded output height.

- [ ] **Step 5: Run frontend/backend UI tests and commit**

~~~bash
cd /tmp/legado-hub-main-merge/backend
pytest -q tests/test_ai_time_serialization.py
cd ../frontend
npm test -- --run src/features/ai/AIWorkspacePage.test.tsx src/lib/time.test.ts
npm run build
cd ..
git add backend/app/core/time.py backend/app/domain/entities/ai_conversation.py backend/app/application/services/novel_agent_app_service.py backend/app/application/services/ai_workspace_service.py backend/tests/test_ai_time_serialization.py frontend/package.json frontend/package-lock.json frontend/src/components/ai/MarkdownMessage.tsx frontend/src/components/ai/ToolResultRenderer.tsx frontend/src/lib/time.ts frontend/src/lib/time.test.ts frontend/src/features/ai/AIWorkspacePage.tsx frontend/src/features/ai/AIWorkspacePage.test.tsx
git commit -m "feat: render evidence-rich GFM novel conversations"
~~~

## Task 9: Full regression, uploaded-book repair and handoff

**Files:**
- Modify only files revealed by failing tests; do not alter unrelated user changes in `/root/legado-hub`.
- Test: `backend/tests/test_novel_analysis_regression_audit.py` and the focused suites above.

- [ ] **Step 1: Run the full backend suite**

~~~bash
cd /tmp/legado-hub-main-merge/backend
pytest -q
~~~

Expected: all existing tests and the new extraction, persistence, vector, adjudicator, learning and time tests pass.

- [ ] **Step 2: Run the full frontend suite and production build**

~~~bash
cd /tmp/legado-hub-main-merge/frontend
npm test -- --run
npm run build
~~~

- [ ] **Step 3: Verify the uploaded book without assuming a title**

Use the running application's owner-scoped novel list endpoint or the configured SQLite read-only query to identify the uploaded book, then run one bounded index worker iteration. Confirm the book has processed chapters including any `canonical_num=0` chapter, nonzero entity/item counts where evidence exists, no explosion of Cartesian relationships, and a completed or explicitly disabled vector status.

- [ ] **Step 4: Inspect the generated knowledge through Agent tools**

Issue read-only queries for one character, one item, one event timeline and one evidence excerpt. Confirm every response contains the selected book boundary, chapter reference and evidence. Confirm a repeated query uses the cache and does not call the adjudicator again.

- [ ] **Step 5: Commit final verification and push `main`**

~~~bash
cd /tmp/legado-hub-main-merge
git status --short --branch
git diff --check
git push origin main
~~~

The final handoff must report the implementation commits, test commands and actual results; do not claim the uploaded book is fixed unless the bounded reindex and read-only checks succeed.
