# Dual-Engine Evolution: Source-Writing & Novel Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the novel source-writing engine with heuristic DOM pattern induction (lowering LLM source generation cost by >85%) and the novel analysis engine with algorithmic entity graph, alias clustering, tension segmentation, and structured digest tools (lowering novel LLM analysis tokens by >70% while drastically increasing depth).

**Architecture:** 
- `SourceInductionService`: Deterministic DOM analysis using BeautifulSoup to infer `ruleToc`, `ruleContent`, and `ruleSearch` directly from HTML.
- `NovelCodeAnalysisService` & `NovelSceneTensionService`: Enhanced entity extraction with alias resolution, character centrality, and sliding-window conflict/climax scene detection.
- `NovelAgentService`: Transition from raw text dump prompts to structured digest payloads and lightweight tool interfaces.

**Tech Stack:** Python 3.10+, FastAPI, BeautifulSoup4, lxml, SQLite, Pytest.

**Spec:** `/tmp/legado-hub/docs/design/2026-09-06-dual-engine-evolution.md`

## Global Constraints
- Strictly code-first and deterministic where possible; LLM is called only for high-level synthesis or when algorithmic confidence is below threshold.
- Zero API key or secret leakage into git, logs, or reports.
- TDD required: RED -> GREEN -> REFACTOR for every task.
- Full backwards compatibility with existing LegadoHub APIs and schemas.

---

### Task 1: Heuristic DOM Pattern Induction for Source Writing

**Files:**
- Create: `backend/app/application/services/source_induction_service.py`
- Test: `backend/tests/test_source_induction_service.py`

**Interfaces:**
- Produces: `SourceInductionService.infer_source_from_html(base_url: str, toc_html: str, content_html: str | None = None, search_html: str | None = None) -> dict`
- Produces: `SourceInductionService.infer_toc_rule(soup: BeautifulSoup) -> dict`
- Produces: `SourceInductionService.infer_content_rule(soup: BeautifulSoup) -> dict`
- Produces: `SourceInductionService.infer_search_rule(soup: BeautifulSoup, base_url: str) -> dict`

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_source_induction_service.py` testing TOC selector induction, content container detection, and search URL extraction on realistic mock HTML.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_source_induction_service.py -q`

- [ ] **Step 3: Write minimal implementation**
Implement `backend/app/application/services/source_induction_service.py` with link density calculations, text-to-tag ratio analysis, and search form parsing.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_source_induction_service.py -q`

- [ ] **Step 5: Commit**
Commit changes with message `feat: add heuristic DOM pattern induction service for source writing`.

---

### Task 2: Integrate Source Induction into Tool Executor and Generator

**Files:**
- Modify: `backend/app/services/generator.py`
- Modify: `backend/app/application/services/source_build_tool_executor.py`
- Test: `backend/tests/test_source_induction_integration.py`

**Interfaces:**
- Consumes: `SourceInductionService` from Task 1.
- Produces: Enhanced `generate_source_from_url` and tool `infer_source_rules`.

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_source_induction_integration.py` to verify that `generator.py` and tool executor use `SourceInductionService` to produce rich Legado rules without LLM dependency.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_source_induction_integration.py -q`

- [ ] **Step 3: Write minimal implementation**
Integrate `SourceInductionService` into `generator.py` and `source_build_tool_executor.py`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_source_induction_integration.py -q`

- [ ] **Step 5: Commit**
Commit changes with message `feat: integrate heuristic source induction into generator and tool executor`.

---

### Task 3: Novel Code Analysis: Character Alias Resolution & Centrality

**Files:**
- Modify: `backend/app/application/services/novel_code_analysis_service.py`
- Test: `backend/tests/test_novel_character_graph.py`

**Interfaces:**
- Produces: `CharacterCandidate.aliases: list[str]`
- Produces: `CharacterCandidate.importance_tier: str` ('protagonist' | 'major' | 'minor')
- Produces: `NovelCodeAnalysisReport.character_graph: dict`

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_novel_character_graph.py` verifying noise filtering, title prefix patterns, and alias clustering (e.g. "林弦" and "小林").

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_character_graph.py -q`

- [ ] **Step 3: Write minimal implementation**
Update `novel_code_analysis_service.py` with alias clustering, title honorific pattern extraction, and degree centrality ranking.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_character_graph.py -q`

- [ ] **Step 5: Commit**
Commit changes with message `feat: enhance novel character entity graph with alias resolution and centrality`.

---

### Task 4: Novel Scene Tension & Climax Segmenter

**Files:**
- Create: `backend/app/application/services/novel_scene_tension_service.py`
- Test: `backend/tests/test_novel_scene_tension.py`

**Interfaces:**
- Produces: `NovelSceneTensionService.calculate_tension_curve(text: str) -> list[float]`
- Produces: `NovelSceneTensionService.extract_climax_scenes(chapters: list[dict], top_k: int = 3) -> list[dict]`

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_novel_scene_tension.py` testing tension scoring on conflict vs tranquil passages and top-K scene extraction.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_scene_tension.py -q`

- [ ] **Step 3: Write minimal implementation**
Implement `backend/app/application/services/novel_scene_tension_service.py` using sliding-window conflict/tension density algorithms.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_scene_tension.py -q`

- [ ] **Step 5: Commit**
Commit changes with message `feat: add novel scene tension and climax segmenter service`.

---

### Task 5: High-Density Structured Digest & Token Reduction for LLM Analysis

**Files:**
- Modify: `backend/app/application/services/novel_agent_service.py`
- Test: `backend/tests/test_novel_structural_digest.py`

**Interfaces:**
- Produces: `NovelAgentService._build_structural_digest(ingestion: NovelIngestion) -> dict`
- Validates: Input payload tokens reduced by >70% compared to 12k raw text dump while preserving character graph and climax highlights.

- [ ] **Step 1: Write the failing test**
Create `backend/tests/test_novel_structural_digest.py` asserting that the built payload contains the character graph, climax scenes, timeline events, and fits within 3,500 characters (~1,800 tokens).

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_structural_digest.py -q`

- [ ] **Step 3: Write minimal implementation**
Update `NovelAgentService._build_payload` to utilize `NovelCodeAnalysisService` and `NovelSceneTensionService` to assemble a dense `NovelStructuralDigest`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_structural_digest.py -q`

- [ ] **Step 5: Commit**
Commit changes with message `feat: condense novel LLM analysis payload with structured digest and tools`.

---

### Task 6: Full Regression Verification & Live Docker Validation

**Files:**
- Tests: `backend/tests/`
- Root: `tests/`

- [ ] **Step 1: Run full backend test suite**
Run: `pytest backend/ -q`
Expected: 100% passing.

- [ ] **Step 2: Run root contract tests**
Run: `pytest tests -q`
Expected: 100% passing.

- [ ] **Step 3: Rebuild and deploy API container**
Run: `docker compose up -d --build api`

- [ ] **Step 4: Verify end-to-end execution with live novels**
Execute analysis on Book 1 and Book 2 and measure token reduction and speedup.

- [ ] **Step 5: Commit and push to origin/feat/slim-docker-deployment**
Commit and push all changes.
