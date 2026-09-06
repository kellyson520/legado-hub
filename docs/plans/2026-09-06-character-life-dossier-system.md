# Novel Character Life Dossier & Item Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a comprehensive novel character lifecycle profiling system combining deterministic code algorithms (item tracking, timeline, emotional arc, multidimensional scoring) with a memory vector store and LLM synthesis to extract deep character dossiers without hallucination.

**Architecture:**
- `ItemTrackerService`: Extracts artifacts, weapons, and items associated with characters and tracks state changes.
- `EmotionalArcService`: Computes per-chapter sentiment, psychological tension, and turning points.
- `CharacterScoringService`: Evaluates Mental, Power, and Plot Impact scores with tier classification (S/A/B/C).
- `CharacterMemoryVectorStore`: Stores scene memory embeddings with hybrid retrieval (entity filter + cosine semantic search).
- `CharacterDossierService`: Aggregates code signals into a Character Dossier and orchestrates LLM synthesis.

**Tech Stack:** Python 3.10+, FastAPI, SQLite, Pytest.

**Spec:** `/tmp/legado-hub/docs/design/2026-09-06-character-life-dossier-system.md`

## Global Constraints
- Zero API key or secret leakage into git, logs, or reports.
- TDD required: RED -> GREEN -> REFACTOR for every task.
- Full backwards compatibility with existing LegadoHub APIs and schemas.

---

### Task 1: Item & Artifact Tracking Service (TDD)

**Files:**
- Create: `backend/app/application/services/novel_item_tracker_service.py`
- Test: `backend/tests/test_novel_item_tracker.py`

**Interfaces:**
- Produces: `ItemTrackerService.track_items(chapters: list[dict], character_names: list[str]) -> dict[str, list[dict]]`
- Output item dict: `{"item_name": str, "action": str, "chapter_index": int, "chapter_title": str, "excerpt": str}`

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_novel_item_tracker.py` testing detection of items (e.g. C4炸药, 奥特曼面具, 冲锋枪) and character attribution.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_item_tracker.py -q`

- [ ] **Step 3: Write minimal implementation**
Implement `ItemTrackerService` in `backend/app/application/services/novel_item_tracker_service.py`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_item_tracker.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: add novel item and artifact tracking service`.

---

### Task 2: Character Emotional Arc & Psychological Trajectory (TDD)

**Files:**
- Create: `backend/app/application/services/novel_emotional_arc_service.py`
- Test: `backend/tests/test_novel_emotional_arc.py`

**Interfaces:**
- Produces: `EmotionalArcService.compute_arc(chapters: list[dict], character_name: str) -> dict[str, Any]`
- Output dict: `{"trajectory": list[dict], "dominant_sentiment": str, "turning_points": list[dict]}`

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_novel_emotional_arc.py` testing emotional trajectory across chapters.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_emotional_arc.py -q`

- [ ] **Step 3: Write minimal implementation**
Implement `EmotionalArcService` in `backend/app/application/services/novel_emotional_arc_service.py`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_emotional_arc.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: add novel character emotional arc and sentiment trajectory service`.

---

### Task 3: Multi-Dimensional Character Scoring & Tiering (TDD)

**Files:**
- Create: `backend/app/application/services/novel_character_scoring_service.py`
- Test: `backend/tests/test_novel_character_scoring.py`

**Interfaces:**
- Produces: `CharacterScoringService.evaluate(character: CharacterCandidate, items: list[dict], arc: dict) -> dict[str, Any]`
- Output dict: `{"mental_score": float, "power_score": float, "plot_impact": float, "overall_tier": str}`

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_novel_character_scoring.py` testing multi-dimensional scoring on protagonist vs minor characters.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_character_scoring.py -q`

- [ ] **Step 3: Write minimal implementation**
Implement `CharacterScoringService` in `backend/app/application/services/novel_character_scoring_service.py`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_character_scoring.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: add multi-dimensional character scoring and tiering service`.

---

### Task 4: Character Memory Vector Store & Hybrid Retrieval (TDD)

**Files:**
- Create: `backend/app/application/services/novel_character_memory_service.py`
- Test: `backend/tests/test_novel_character_memory.py`

**Interfaces:**
- Produces: `CharacterMemoryService.index_character_scenes(book_id: int, chapters: list[dict], character_names: list[str]) -> int`
- Produces: `CharacterMemoryService.hybrid_query(book_id: int, character_name: str, query_text: str, top_k: int = 3) -> list[dict]`

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_novel_character_memory.py` asserting indexing of character memories and hybrid semantic query.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_character_memory.py -q`

- [ ] **Step 3: Write minimal implementation**
Implement `CharacterMemoryService` in `backend/app/application/services/novel_character_memory_service.py`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_character_memory.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: add character memory vector store and hybrid retrieval service`.

---

### Task 5: Comprehensive Character Dossier Aggregator & LLM Integration (TDD)

**Files:**
- Create: `backend/app/application/services/novel_character_dossier_service.py`
- Modify: `backend/app/interfaces/http/novel.py`
- Test: `backend/tests/test_novel_character_dossier.py`

**Interfaces:**
- Produces: `CharacterDossierService.build_dossier(book_id: int, character_name: str, chapters: list[dict]) -> dict[str, Any]`
- HTTP Route: `GET /api/novel/books/{book_id}/character/{character_name}/dossier`

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_novel_character_dossier.py` testing full dossier aggregation (timeline, items, emotions, score, memories) and endpoint.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_character_dossier.py -q`

- [ ] **Step 3: Write minimal implementation**
Implement `CharacterDossierService` and expose HTTP endpoint in `novel.py`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_character_dossier.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: add character dossier aggregation service and HTTP endpoint`.

---

### Task 6: Live Validation on Real Novels (林弦 & 杨间) & Full Regression

**Files:**
- Tests: `backend/tests/`
- Docker: API rebuild

- [ ] **Step 1: Run full backend test suite**
Run: `pytest backend/ -q`
Expected: 100% passing.

- [ ] **Step 2: Run root contract tests**
Run: `pytest tests -q`
Expected: 100% passing.

- [ ] **Step 3: Rebuild and deploy API container**
Run: `docker compose up -d --build api`

- [ ] **Step 4: Execute real character dossier extraction via API on 林弦 and 杨间**
Verify item tracking, emotional arc, and scoring on real database chapters.

- [ ] **Step 5: Commit and push to origin/feat/slim-docker-deployment**
Commit and push all changes.
