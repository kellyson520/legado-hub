# Universal Linguistic Matrix Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the novel analysis and character extraction algorithms from closed-vocabulary wordlists to an open-vocabulary linguistic morphology and syntactic frame system, and replace basic scores with a 6-dimensional capability matrix and 8-dimensional affective space, verified across classical (Three Kingdoms), modern mystery, and supernatural genres.

**Architecture:**
- `NovelItemTrackerService`: Upgraded with Classifier Syntactic Slots, Action Governed Slots, and Morphological Stem Filters (handles 青龙偃月刀, 赤兔马, 方天画戟, C4炸药, 鬼眼 without hardcoded lists).
- `NovelCodeAnalysisService`: Upgraded with Classical Chinese Dialogue Frames (叹曰, 笑曰, 喝道, 叱曰) and Courtesy Titles/Official Ranks (云长, 关公, 丞相, 主公).
- `NovelEmotionalArcService`: Upgraded with an 8-dimensional classical & modern affective tensor (喜怒哀惧忠雄疑溃).
- `NovelCharacterScoringService`: Upgraded to output the full 6-dimensional capability matrix (武勇绝杀, 智谋策论, 统御声望, 气节风骨, 宝器神兵, 命途支配) with SSS/SS/S/A/B/C tiering.
- `NovelCharacterDossierService`: Updated to render the comprehensive 6D matrix and multi-genre profiles.

**Tech Stack:** Python 3.10+, FastAPI, Pytest, Regex.

**Spec:** `/tmp/legado-hub/docs/design/2026-09-06-universal-linguistic-matrix-evolution.md`

## Global Constraints
- Zero API key or secret leakage into git, logs, or reports.
- TDD required: RED -> GREEN -> REFACTOR for every task.
- Zero backwards incompatibility; preserve existing return structure while expanding capabilities.

---

### Task 1: Open-Vocabulary Item Extraction via Linguistic Morphology (TDD)

**Files:**
- Modify: `backend/app/application/services/novel_item_tracker_service.py`
- Test: `backend/tests/test_novel_open_item_tracker.py`

- [ ] **Step 1: Write failing test**
Create `backend/tests/test_novel_open_item_tracker.py` asserting that items like "青龙偃月刀", "赤兔马", "丈八蛇矛", "雌雄双股剑", "方天画戟" are extracted via syntactic frames and assigned correct item categories (weapon, mount, artifact).

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_open_item_tracker.py -q`

- [ ] **Step 3: Implement open-vocabulary morphological extractor**
Add classifier slot patterns and action governed slots with stem filters to `NovelItemTrackerService`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_open_item_tracker.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: add open-vocabulary morphological item extraction`.

---

### Task 2: Cross-Genre Character Extraction & Classical Dialogue Frames (TDD)

**Files:**
- Modify: `backend/app/application/services/novel_code_analysis_service.py`
- Test: `backend/tests/test_novel_classical_character.py`

- [ ] **Step 1: Write failing test**
Create `backend/tests/test_novel_classical_character.py` testing classical dialogue verbs (叹曰, 笑曰, 叱曰, 喝道, 纵马, 引兵) and titles (关公, 云长, 丞相, 玄德).

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_classical_character.py -q`

- [ ] **Step 3: Implement classical syntactic frames**
Extend patterns in `NovelCodeAnalysisService` to recognize classical dialogue frames, courtesy titles, and alias clustering.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_classical_character.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: support classical Chinese dialogue frames and courtesy name clustering`.

---

### Task 3: Eight-Dimensional Affective Tension Space (TDD)

**Files:**
- Modify: `backend/app/application/services/novel_emotional_arc_service.py`
- Test: `backend/tests/test_novel_affective_space.py`

- [ ] **Step 1: Write failing test**
Create `backend/tests/test_novel_affective_space.py` testing 8-axis emotion vectors (喜怒哀惧忠雄疑溃).

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_affective_space.py -q`

- [ ] **Step 3: Implement 8-axis affective space**
Update `NovelEmotionalArcService` with multi-axis affect tensor and sentiment shifts.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_affective_space.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: expand character emotional arc into eight-dimensional affective space`.

---

### Task 4: Six-Dimensional Comprehensive Capability Matrix & Tiering (TDD)

**Files:**
- Modify: `backend/app/application/services/novel_character_scoring_service.py`
- Test: `backend/tests/test_novel_six_dimension_matrix.py`

- [ ] **Step 1: Write failing test**
Create `backend/tests/test_novel_six_dimension_matrix.py` asserting 6-axis matrix (武勇绝杀, 智谋策论, 统御声望, 气节风骨, 宝器神兵, 命途支配) and SSS/SS/S/A/B/C tiering.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_six_dimension_matrix.py -q`

- [ ] **Step 3: Implement 6D capability matrix**
Update `NovelCharacterScoringService` with comprehensive 6-axis evaluations.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_six_dimension_matrix.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: upgrade character scoring to six-dimensional capability matrix`.

---

### Task 5: Integration & Cross-Genre Verification (Three Kingdoms + Luna + Resurrection)

**Files:**
- Modify: `backend/app/application/services/novel_character_dossier_service.py`
- Test: `backend/tests/test_novel_cross_genre_dossier.py`

- [ ] **Step 1: Write failing test**
Create `backend/tests/test_novel_cross_genre_dossier.py` testing full Guan Yu dossier (青龙偃月刀, 赤兔马, 温酒斩华雄, 义薄云天, S/SS 级) and modern compatibility.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_novel_cross_genre_dossier.py -q`

- [ ] **Step 3: Update Character Dossier Service**
Connect 6D matrix, 8D affect tensor, and open items into dossier rendering.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_novel_cross_genre_dossier.py -q`

- [ ] **Step 5: Commit**
Commit with message `feat: integrate 6D matrix and open vocabulary into character dossier`.

---

### Task 6: Live Container Build, API Verification & Git Sync

**Files:**
- Full suite verification
- Docker compose rebuild

- [ ] **Step 1: Run full test suites**
Run: `python3 -m pytest tests -q` and `cd backend && python3 -m pytest -q`.

- [ ] **Step 2: Rebuild API docker container**
Run: `docker compose up -d --build api` and verify healthy status.

- [ ] **Step 3: Live API verification across genres**
Test live API on classical Guan Yu passage and existing database novels.

- [ ] **Step 4: Commit and push to origin/feat/slim-docker-deployment**
Push clean commits to remote.
