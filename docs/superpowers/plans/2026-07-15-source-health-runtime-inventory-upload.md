# Runtime Source Health Inventory and JSON Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the published runtime book source in the health console backed by the temporary database, and let operators import Legado JSON from a local file as well as pasted JSON.

**Architecture:** The runtime source workflow persists `source_versions`, while health probing consumes legacy `book_sources`. Add an idempotent bridge that registers valid published runtime book payloads as `book_sources`, invoke it after publication and at FastAPI startup, then make health listing include all registered book sources with an `unknown/not_probed` synthetic row where no snapshot exists. The browser reads the selected `.json` file locally, validates it with the same parser as pasted JSON, and submits only the parsed JSON to the existing `/api/sources/import` endpoint.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, pytest + pytest-asyncio, React 18, TypeScript, Vitest, Testing Library.

---

### Task 1: Bridge published runtime sources into the probe inventory

**Files:**
- Modify: `backend/app/application/services/source_runtime_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_source_rule_editor_service.py`
- Test: `backend/tests/test_source_build_lifespan.py`

- [ ] **Step 1: Write failing runtime-publish and startup-sync tests**

```python
@pytest.mark.asyncio
async def test_publish_rule_version_registers_published_book_for_health_probe(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "runtime-bridge.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    service = build_source_runtime_service()
    draft = await service.create_rule_draft(...)
    await service.validate_rule_version(draft["source_version_id"], "1")
    await service.publish_rule_version(draft["source_version_id"], "1")
    rows = await build_source_repository().list_book_sources_full(
        urls=["https://books.example.test"]
    )
    assert rows[0]["bookSourceName"] == "示例书源"

def test_app_lifespan_registers_existing_published_runtime_book_sources(monkeypatch, tmp_path):
    # Seed a published SourceVersion without a BookSourceModel, run lifespan,
    # and assert the source inventory contains the matching URL exactly once.
```

- [ ] **Step 2: Run the focused tests to verify the bridge is absent**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_source_rule_editor_service.py backend/tests/test_source_build_lifespan.py -q`

Expected: FAIL because publication and startup do not create `book_sources` entries.

- [ ] **Step 3: Add the idempotent bridge**

```python
# SourceRuntimeService.__init__ receives an optional book_source_repo.
async def sync_published_book_sources(self) -> int:
    if self._book_source_repo is None:
        return 0
    payloads = []
    for version in self._repo.list_published_versions():
        if version.source_type != "book":
            continue
        name = version.payload.get("bookSourceName")
        url = version.payload.get("bookSourceUrl")
        if isinstance(name, str) and name.strip() and isinstance(url, str) and url.strip():
            payloads.append({**version.payload, "bookSourceName": name.strip(), "bookSourceUrl": url.strip()})
    return await self._book_source_repo.upsert_book_sources(payloads, actor_id=0) if payloads else 0
```

Call `sync_published_book_sources()` after `publish_rule_version()` and `resolve_review(..., action="publish")`; wire `build_source_runtime_service()` with `build_source_repository()`; call the method once during FastAPI lifespan startup before workers begin. Do not copy failed/candidate versions and do not change their status.

- [ ] **Step 4: Run the focused tests to verify the bridge passes**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_source_rule_editor_service.py backend/tests/test_source_build_lifespan.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the bridge**

```bash
git add backend/app/application/services/source_runtime_service.py backend/app/infrastructure/persistence/factory.py backend/app/main.py backend/tests/test_source_rule_editor_service.py backend/tests/test_source_build_lifespan.py
git commit -m "fix: register published runtime sources for health probes"
```

### Task 2: List unprobed sources in the health API

**Files:**
- Modify: `backend/app/application/services/source_health_admin_service.py`
- Test: `backend/tests/test_source_health_admin_service.py`

- [ ] **Step 1: Write a failing health-list test**

```python
@pytest.mark.asyncio
async def test_health_list_includes_registered_source_without_snapshot(monkeypatch, tmp_path):
    # Seed one BookSourceModel and no SourceHealthSnapshot.
    result = await service.list_book_source_health(page=1, page_size=20)
    assert result["meta"]["total"] == 1
    assert result["items"][0]["health_status"] == "unknown"
    assert result["items"][0]["failure_reason"] == "not_probed"
    assert result["items"][0]["route_policy"] == "probe_only"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_source_health_admin_service.py::test_health_list_includes_registered_source_without_snapshot -q`

Expected: FAIL because `list_book_source_health` reads only snapshot rows.

- [ ] **Step 3: Implement inventory-first health serialization**

Make `list_book_source_health` page through `source_repo.list_book_sources`, obtain each snapshot by `source_id`, and serialize either the real snapshot or an in-memory `SourceHealthSnapshot` with `unknown` stages, `failure_reason="not_probed"`, and `route_policy="probe_only"`. Apply `statuses` after deriving each row, then calculate pagination metadata from the filtered inventory. Preserve probe/recover endpoints and stored snapshots unchanged.

- [ ] **Step 4: Run health API service tests**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_source_health_admin_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the inventory fix**

```bash
git add backend/app/application/services/source_health_admin_service.py backend/tests/test_source_health_admin_service.py
git commit -m "fix: include unprobed sources in health inventory"
```

### Task 3: Add JSON file selection to the source import UI

**Files:**
- Modify: `frontend/src/features/sources/SourceListPage.tsx`
- Modify: `frontend/src/features/sources/SourceListPage.test.tsx`

- [ ] **Step 1: Write a failing file-import test**

```tsx
test('source list imports a selected Legado JSON file', async () => {
  render(<MemoryRouter><SourceListPage /></MemoryRouter>)
  const file = new File([
    '[{"bookSourceName":"文件书源","bookSourceUrl":"https://file.example"}]'
  ], 'legado.json', { type: 'application/json' })
  fireEvent.change(await screen.findByLabelText('选择 Legado JSON 文件'), {
    target: { files: [file] },
  })
  await waitFor(() => expect(importLegadoSources).toHaveBeenCalledWith([
    { bookSourceName: '文件书源', bookSourceUrl: 'https://file.example' },
  ]))
})
```

- [ ] **Step 2: Run the UI test to verify it fails**

Run: `npm test -- --run src/features/sources/SourceListPage.test.tsx`

Expected: FAIL because the page has no file input or reader.

- [ ] **Step 3: Implement local-file parsing with the existing import request**

Add a labelled `<input type="file" accept="application/json,.json">` beside the existing textarea. Factor JSON parsing and submission into one helper used by both form submit and file change. Reject an empty/non-JSON file with an inline error; leave the chosen text in the textarea for inspection; do not upload raw file bytes or create a new backend endpoint.

- [ ] **Step 4: Run source UI tests and production build**

Run: `npm test -- --run src/features/sources/SourceListPage.test.tsx src/features/sources/SourceListImportLink.test.tsx && npm run build`

Expected: all tests pass and Vite produces `dist/`.

- [ ] **Step 5: Commit the UI improvement**

```bash
git add frontend/src/features/sources/SourceListPage.tsx frontend/src/features/sources/SourceListPage.test.tsx
git commit -m "feat: import Legado sources from JSON files"
```

### Task 4: Run cross-layer verification and deploy the release

**Files:**
- Test: `backend/tests/test_source_rule_editor_service.py`
- Test: `backend/tests/test_source_health_admin_service.py`
- Test: `backend/tests/test_source_build_lifespan.py`
- Test: `frontend/src/features/sources/SourceListPage.test.tsx`
- Test: `frontend/src/features/sources/SourceListImportLink.test.tsx`

- [ ] **Step 1: Run focused backend regression tests**

Run: `/tmp/legado-hub-pytest-venv/bin/python -m pytest backend/tests/test_source_rule_editor_service.py backend/tests/test_source_health_admin_service.py backend/tests/test_source_build_lifespan.py -q`

Expected: PASS.

- [ ] **Step 2: Run frontend tests and build**

Run: `npm test -- --run src/features/sources/SourceListPage.test.tsx src/features/sources/SourceListImportLink.test.tsx src/features/sources/SourceHealthPage.test.tsx && npm run build`

Expected: PASS and build exit code 0.

- [ ] **Step 3: Verify the live temporary database after restart**

Run: `curl --silent --show-error --fail http://127.0.0.1:8000/api/status`

Expected: a successful health envelope; after authenticated page load, the inventory lists 八叉书库 as `unknown/not_probed` until it is probed.

- [ ] **Step 4: Commit and push the final verified change**

```bash
git add backend frontend
git commit -m "fix: surface runtime sources in health inventory"
git push origin main
```

### Task 5: Make source inventory and health pagination visible in the console

**Files:**
- Modify: `frontend/src/api/modules/sources.ts`
- Modify: `frontend/src/features/sources/SourceListPage.tsx`
- Modify: `frontend/src/features/sources/SourceListPage.test.tsx`
- Modify: `frontend/src/features/sources/SourceHealthPage.tsx`
- Modify: `frontend/src/features/sources/SourceHealthPage.test.tsx`

- [ ] **Step 1: Write failing API-contract and pagination tests**

```tsx
test('source inventory renders the legacy book-source response fields', async () => {
  // Mock bookSourceName/bookSourceUrl/sourceStatus and assert name + status render.
})

test('health console requests and navigates inventory pages using API meta', async () => {
  // First response has meta { page: 1, page_size: 20, total: 21 }.
  // Click Next and assert listSourceHealth receives page: 2, page_size: 20.
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- --run src/features/sources/SourceListPage.test.tsx src/features/sources/SourceHealthPage.test.tsx`

Expected: FAIL because source cards read the incompatible runtime-shaped fields and health page is permanently hard-coded to page one.

- [ ] **Step 3: Implement contract mapping and bounded page navigation**

Map `/sources/book_sources` legacy records (`bookSourceName`, `bookSourceUrl`, `sourceStatus`) to the display model without claiming unavailable runtime version/grade values. In the health page, retain response meta, show inventory total from `meta.total`, request the selected page, and add disabled Previous/Next buttons with an accessible page indicator. Do not fetch all pages or change backend APIs.

- [ ] **Step 4: Run frontend tests and build**

Run: `npm test -- --run src/features/sources/SourceListPage.test.tsx src/features/sources/SourceHealthPage.test.tsx && npm run build`

Expected: PASS and production build exit code 0.

- [ ] **Step 5: Commit the console correction**

```bash
git add frontend/src/api/modules/sources.ts frontend/src/features/sources/SourceListPage.tsx frontend/src/features/sources/SourceListPage.test.tsx frontend/src/features/sources/SourceHealthPage.tsx frontend/src/features/sources/SourceHealthPage.test.tsx
git commit -m "fix: page source health inventory in console"
```
