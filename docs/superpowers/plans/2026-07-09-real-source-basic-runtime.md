# Real Source Basic Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the local `测试源/shareBookSource.json` dataset to the new main API, then deliver a working basic runtime flow for source import, real search, multi-source complement, quality selection, and character calibration for `捞尸人` and `斗罗大陆`.

**Architecture:** Reuse the existing `LegadoBookSourceFetcher` for live `search -> toc -> content`, reuse `SourceComplementService` and `ContentMerger` for multi-source correction, and reuse the provider-backed AI runtime for character calibration. Keep all new runtime surfaces under the authenticated main API in `app/interfaces/http/`, and use local smoke scripts under `backend/scripts/` for true end-to-end verification against the local source file.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, SQLite, httpx/aiohttp, BeautifulSoup, lxml, pytest, pytest-asyncio, React + Vite

---

> **Git note:** this working copy currently has no `.git`. Replace each “Commit” step with a filesystem checkpoint under `docs/superpowers/reports/checkpoints/`.

## File Structure

```text
backend/app/
├── domain/repositories/
│   └── source_repo.py                               # bulk import / full-source loading contract
├── application/services/
│   ├── source_service.py                            # source catalog CRUD + local file import
│   ├── source_read_service.py                       # real search / toc / content / title smoke
│   ├── source_complement_app_service.py             # chapter alignment + complement + quality selection
│   └── character_calibration_service.py             # provider-backed character normalization
├── infrastructure/persistence/sqlite/
│   ├── schema.py                                    # enrich book_sources columns for full Legado payload
│   └── source_repo_impl.py                          # bulk upsert + full payload serialization
├── infrastructure/persistence/
│   └── factory.py                                   # build source/read/complement/calibration services
├── interfaces/http/
│   ├── sources.py                                   # import/export/list source catalog
│   ├── reading.py                                   # runtime search / toc / content / complement / calibrate
│   └── router.py
backend/scripts/
├── import_share_book_sources.py                     # local file import helper
├── search_real_books.py                             # 捞尸人 / 斗罗大陆 search smoke
├── smoke_source_complement.py                       # multi-source complement smoke
└── smoke_character_calibration.py                   # character calibration smoke
backend/tests/
├── test_source_import_main_api.py
├── test_source_read_service.py
├── test_source_complement_api.py
├── test_character_calibration_api.py
└── test_share_book_source_smoke.py
frontend/src/
├── api/modules/sources.ts
├── api/modules/reading.ts
├── features/sources/SourceListPage.tsx
├── features/reading/ReadingWorkbenchPage.tsx
├── app/router.tsx
└── features/reading/ReadingWorkbenchPage.test.tsx
```

### Task 1: Enrich source persistence and import local `shareBookSource.json`

**Files:**
- Modify: `backend/app/domain/repositories/source_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/source_repo_impl.py`
- Modify: `backend/app/application/services/source_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/interfaces/http/sources.py`
- Create: `backend/tests/test_source_import_main_api.py`

- [ ] **Step 1: Write the failing tests**

```python
from fastapi.testclient import TestClient


def test_import_book_sources_from_local_file_persists_legado_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-import.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    sample_file = tmp_path / "shareBookSource.json"
    sample_file.write_text(
        """
        [
          {
            "bookSourceName": "测试源A",
            "bookSourceUrl": "https://a.example.com",
            "bookSourceGroup": "本地导入",
            "enabled": true,
            "searchUrl": "https://a.example.com/search?key={{key}}",
            "ruleSearch": {"bookList": ".book", "name": ".title", "bookUrl": "a@href"},
            "ruleToc": {"chapterList": "#list a", "chapterName": "text", "chapterUrl": "href"},
            "ruleContent": {"content": "#content"}
          }
        ]
        """,
        encoding="utf-8",
    )

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token({"sub": "1", "permissions": ["book_sources.write", "book_sources.read"], "sid": "src-import-1"})
    response = client.post(
        "/api/sources/book_sources/import",
        json={"file_path": str(sample_file), "replace_existing": True},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["book_count"] == 1
    assert payload["file_path"] == str(sample_file)

    listed = client.get(
        "/api/sources/book_sources",
        headers={"Authorization": f"Bearer {token}"},
    )
    first = listed.json()["data"][0]
    assert first["searchUrl"] == "https://a.example.com/search?key={{key}}"
    assert first["ruleSearch"]["bookList"] == ".book"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_source_import_main_api.py -v`  
Expected: FAIL because the main API has no local-file import endpoint and the new SQLite source schema only stores a minimal subset of fields.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/domain/repositories/source_repo.py
class SourceRepository(ABC):
    @abstractmethod
    async def upsert_book_sources(self, items: list[dict], actor_id: int) -> int:
        raise NotImplementedError

    @abstractmethod
    async def list_book_sources_full(
        self,
        enabled_only: bool = False,
        ids: list[int] | None = None,
        urls: list[str] | None = None,
    ) -> list[dict]:
        raise NotImplementedError
```

```python
# backend/app/infrastructure/persistence/sqlite/schema.py
class BookSourceModel(Base):
    __tablename__ = "book_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bookSourceName = Column(String, nullable=False)
    bookSourceUrl = Column(String, nullable=False, unique=True, index=True)
    bookSourceGroup = Column(String, nullable=False, default="default")
    bookSourceType = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    searchUrl = Column(Text, nullable=True)
    ruleSearch = Column(Text, nullable=False, default="{}")
    ruleBookInfo = Column(Text, nullable=False, default="{}")
    ruleToc = Column(Text, nullable=False, default="{}")
    ruleContent = Column(Text, nullable=False, default="{}")
    header = Column(Text, nullable=True)
    bookSourceComment = Column(Text, nullable=True)
    sourceStatus = Column(String, nullable=False, default="unknown")
    sourceOrigin = Column(Text, nullable=True)
    lastCheckTime = Column(DateTime, nullable=True)
    errorMsg = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

```python
# backend/app/application/services/source_service.py
class SourceAppService:
    async def import_book_sources_from_file(self, file_path: str, actor_id: int, replace_existing: bool = True) -> dict:
        text = Path(file_path).read_text(encoding="utf-8")
        parser = SourceFetcher()
        book_sources, _ = parser.parse_sources_from_text(text, origin=file_path)
        if replace_existing:
            imported = await self._repo.upsert_book_sources(book_sources, actor_id)
        else:
            existing = await self._repo.list_book_sources_full(urls=[item["bookSourceUrl"] for item in book_sources])
            existing_urls = {item["bookSourceUrl"] for item in existing}
            filtered = [item for item in book_sources if item["bookSourceUrl"] not in existing_urls]
            imported = await self._repo.upsert_book_sources(filtered, actor_id)
        return {"file_path": file_path, "book_count": imported}
```

```python
# backend/app/interfaces/http/sources.py
class LocalBookSourceImportRequest(BaseModel):
    file_path: str
    replace_existing: bool = True


@router.post("/book_sources/import")
async def import_book_sources(
    payload: LocalBookSourceImportRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_service()
    data = await service.import_book_sources_from_file(
        payload.file_path,
        identity.user_id,
        replace_existing=payload.replace_existing,
    )
    return {"success": True, "code": "OK", "message": "book sources imported", "data": data, "meta": {}, "trace_id": None}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_source_import_main_api.py -v`  
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/interfaces/http/sources.py docs/superpowers/reports/checkpoints/2026-07-09-real-source-task1.py`  
Expected: checkpoint file exists.

### Task 2: Add real search / toc / content runtime using imported Legado sources

**Files:**
- Create: `backend/app/application/services/source_read_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Create: `backend/app/interfaces/http/reading.py`
- Modify: `backend/app/interfaces/http/router.py`
- Create: `backend/tests/test_source_read_service.py`
- Create: `backend/scripts/import_share_book_sources.py`
- Create: `backend/scripts/search_real_books.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest


class FakeFetcher:
    async def search(self, source: dict, keyword: str, page: int = 1):
        return [{
            "name": keyword,
            "author": "测试作者",
            "bookUrl": source["bookSourceUrl"] + "/book/1",
            "sourceName": source["bookSourceName"],
            "sourceUrl": source["bookSourceUrl"],
            "_source_config": source,
        }]

    async def get_toc(self, source: dict, book_url: str):
        return [{"title": "第一章 入世", "url": book_url + "/1"}]

    async def get_content(self, source: dict, chapter_url: str):
        return {"content": "这是正文内容。", "title": "第一章 入世", "nextUrl": ""}


@pytest.mark.asyncio
async def test_source_read_service_runs_search_toc_and_content():
    from app.application.services.source_read_service import SourceReadService

    class FakeRepo:
        async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
            return [{
                "id": 1,
                "bookSourceName": "测试源A",
                "bookSourceUrl": "https://a.example.com",
                "enabled": True,
                "searchUrl": "https://a.example.com/search?key={{key}}",
                "ruleSearch": {"bookList": ".book", "name": ".title", "bookUrl": "a@href"},
                "ruleToc": {"chapterList": "#list a", "chapterName": "text", "chapterUrl": "href"},
                "ruleContent": {"content": "#content"},
            }]

    service = SourceReadService(repo=FakeRepo(), fetcher=FakeFetcher())
    results = await service.search_books(keyword="捞尸人")

    assert results["items"][0]["name"] == "捞尸人"
    book = await service.get_book_toc(source_id=1, book_url="https://a.example.com/book/1")
    assert book["chapters"][0]["title"] == "第一章 入世"
    chapter = await service.get_chapter_content(source_id=1, chapter_url="https://a.example.com/book/1/1")
    assert chapter["content"] == "这是正文内容。"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_source_read_service.py -v`  
Expected: FAIL because the runtime read service and `reading` router do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/application/services/source_read_service.py
class SourceReadService:
    def __init__(self, repo, fetcher):
        self._repo = repo
        self._fetcher = fetcher

    async def search_books(self, keyword: str, source_ids: list[int] | None = None, limit_per_source: int = 3) -> dict:
        sources = await self._repo.list_book_sources_full(enabled_only=True, ids=source_ids)
        items: list[dict] = []
        for source in sources:
            found = await self._fetcher.search(source, keyword, page=1)
            for book in found[:limit_per_source]:
                items.append({
                    "source_id": source["id"],
                    "name": book.get("name", ""),
                    "author": book.get("author", ""),
                    "bookUrl": book.get("bookUrl", ""),
                    "sourceName": source["bookSourceName"],
                    "sourceUrl": source["bookSourceUrl"],
                })
        return {"keyword": keyword, "items": items}

    async def get_book_toc(self, source_id: int, book_url: str) -> dict:
        source = (await self._repo.list_book_sources_full(ids=[source_id]))[0]
        chapters = await self._fetcher.get_toc(source, book_url)
        return {"source_id": source_id, "book_url": book_url, "chapters": chapters}

    async def get_chapter_content(self, source_id: int, chapter_url: str) -> dict:
        source = (await self._repo.list_book_sources_full(ids=[source_id]))[0]
        content = await self._fetcher.get_content(source, chapter_url)
        return {"source_id": source_id, "chapter_url": chapter_url, **content}
```

```python
# backend/app/interfaces/http/reading.py
@router.post("/search")
async def search_books(
    payload: ReadingSearchRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_read_service()
    data = await service.search_books(payload.keyword, payload.source_ids, payload.limit_per_source)
    return {"success": True, "code": "OK", "message": "search completed", "data": data["items"], "meta": {"keyword": payload.keyword}, "trace_id": None}
```

```python
# backend/scripts/import_share_book_sources.py
DEFAULT_FILE = Path(__file__).resolve().parents[2] / "测试源" / "shareBookSource.json"
print(f"[import] using file: {DEFAULT_FILE}")
```

```python
# backend/scripts/search_real_books.py
DEFAULT_KEYWORDS = ["捞尸人", "斗罗大陆"]
print(f"[search] keywords: {DEFAULT_KEYWORDS}")
```

- [ ] **Step 4: Run tests and the basic import/search smoke**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_source_read_service.py -v`  
Expected: PASS.

Run: `.\.venv\Scripts\python.exe scripts\import_share_book_sources.py`  
Expected: imports `测试源/shareBookSource.json` into local SQLite and prints imported count.

Run: `.\.venv\Scripts\python.exe scripts\search_real_books.py`  
Expected: prints per-source hits for `捞尸人` and `斗罗大陆` and shows at least one matched source for each title.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/application/services/source_read_service.py docs/superpowers/reports/checkpoints/2026-07-09-real-source-task2.py`  
Expected: checkpoint file exists.

### Task 3: Deliver multi-source complement, chapter alignment, and quality selection

**Files:**
- Create: `backend/app/application/services/source_complement_app_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/interfaces/http/reading.py`
- Create: `backend/tests/test_source_complement_api.py`
- Create: `backend/scripts/smoke_source_complement.py`

- [ ] **Step 1: Write the failing tests**

```python
from fastapi.testclient import TestClient


def test_reading_complement_endpoint_returns_best_quality_chapter(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-complement.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    class FakeComplementService:
        async def complement(self, payload):
            return {
                "book_name": "斗罗大陆",
                "chapter_title": "第一章 斗罗大陆",
                "merge_strategy": "hybrid",
                "quality_choice": "best",
                "final_content": "合并后的高质量正文",
                "quality_score": 92.5,
                "merged_from": ["源A", "源B"],
            }

    from app.interfaces.http import reading
    reading.build_source_complement_app_service = lambda: FakeComplementService()

    client = TestClient(app)
    token = create_access_token({"sub": "1", "permissions": ["book_sources.read"], "sid": "src-comp-1"})
    response = client.post(
        "/api/reading/complement",
        json={"keyword": "斗罗大陆", "chapter_index": 0, "merge_strategy": "hybrid", "quality_choice": "best"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["quality_choice"] == "best"
    assert body["quality_score"] == 92.5
    assert body["merged_from"] == ["源A", "源B"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_source_complement_api.py -v`  
Expected: FAIL because there is no complement app service or `/api/reading/complement` endpoint.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/application/services/source_complement_app_service.py
class SourceComplementAppService:
    def __init__(self, read_service, complement_service):
        self._read_service = read_service
        self._complement_service = complement_service

    async def complement(self, payload: dict) -> dict:
        search = await self._read_service.search_books(payload["keyword"], payload.get("source_ids"), limit_per_source=1)
        candidates = search["items"]
        if not candidates:
            return {"book_name": payload["keyword"], "final_content": "", "quality_score": 0.0, "merged_from": [], "quality_choice": payload["quality_choice"]}

        result = await self._complement_service.complement_chapter(
            book_name=payload["keyword"],
            chapter_title=payload.get("chapter_title", "第1章"),
            chapter_num=payload.get("chapter_index", 0) + 1,
            source_urls=[item["sourceUrl"] for item in candidates],
            reference_content="",
            publish_events=False,
        )
        return {
            "book_name": payload["keyword"],
            "chapter_title": payload.get("chapter_title", "第1章"),
            "merge_strategy": result.merge_strategy,
            "quality_choice": payload["quality_choice"],
            "final_content": result.final_content,
            "quality_score": result.quality_score,
            "merged_from": result.merged_from,
        }
```

```python
# backend/app/interfaces/http/reading.py
class ChapterComplementRequest(BaseModel):
    keyword: str
    chapter_index: int = 0
    source_ids: list[int] | None = None
    merge_strategy: str = "hybrid"
    quality_choice: str = "best"


@router.post("/complement")
async def complement_chapter(
    payload: ChapterComplementRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_complement_app_service()
    data = await service.complement(payload.model_dump())
    return {"success": True, "code": "OK", "message": "chapter complemented", "data": data, "meta": {}, "trace_id": None}
```

```python
# backend/scripts/smoke_source_complement.py
DEFAULT_KEYWORDS = ["捞尸人", "斗罗大陆"]
DEFAULT_MERGE_STRATEGY = "hybrid"
DEFAULT_QUALITY_CHOICE = "best"
print(f"[complement] keywords={DEFAULT_KEYWORDS} strategy={DEFAULT_MERGE_STRATEGY} quality={DEFAULT_QUALITY_CHOICE}")
```

- [ ] **Step 4: Run tests and the multi-source smoke**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_source_complement_api.py -v`  
Expected: PASS.

Run: `.\.venv\Scripts\python.exe scripts\smoke_source_complement.py`  
Expected: for `捞尸人` and `斗罗大陆`, prints matched source count, merged source count, merge strategy, quality score, and a non-empty final content preview when sources are available.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/application/services/source_complement_app_service.py docs/superpowers/reports/checkpoints/2026-07-09-real-source-task3.py`  
Expected: checkpoint file exists.

### Task 4: Add provider-backed character calibration on complemented content

**Files:**
- Create: `backend/app/application/services/character_calibration_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Modify: `backend/app/interfaces/http/reading.py`
- Create: `backend/tests/test_character_calibration_api.py`
- Create: `backend/scripts/smoke_character_calibration.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest


class FakeAIService:
    async def run_character_analysis(self, payload: dict, actor_id: str = "system") -> dict:
        return {
            "id": "ai-task-1",
            "status": "succeeded",
            "provider": "local-llm",
            "model": "gpt-4.1-mini",
            "result": {
                "characters": [
                    {"canonical_name": "唐三", "aliases": ["小三", "三哥"], "confidence": 0.95}
                ]
            },
        }


@pytest.mark.asyncio
async def test_character_calibration_service_returns_canonical_characters():
    from app.application.services.character_calibration_service import CharacterCalibrationService

    class FakeComplementApp:
        async def complement(self, payload):
            return {
                "book_name": payload["keyword"],
                "chapter_title": "第一章 斗罗大陆",
                "final_content": "唐三看见小舞，三哥继续前行。",
                "quality_score": 90.0,
                "merged_from": ["源A", "源B"],
            }

    service = CharacterCalibrationService(complement_service=FakeComplementApp(), ai_service=FakeAIService())
    result = await service.calibrate({"keyword": "斗罗大陆", "chapter_index": 0}, actor_id="admin")

    assert result["provider"] == "local-llm"
    assert result["characters"][0]["canonical_name"] == "唐三"
    assert "三哥" in result["characters"][0]["aliases"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_character_calibration_api.py -v`  
Expected: FAIL because the calibration service and endpoint do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/application/services/character_calibration_service.py
class CharacterCalibrationService:
    def __init__(self, complement_service, ai_service):
        self._complement_service = complement_service
        self._ai_service = ai_service

    async def calibrate(self, payload: dict, actor_id: str) -> dict:
        complemented = await self._complement_service.complement(payload)
        analysis = await self._ai_service.run_character_analysis(
            {
                "title": complemented["book_name"],
                "content": complemented["final_content"],
                "model": payload.get("model", "gpt-4.1-mini"),
            },
            actor_id=actor_id,
        )
        return {
            "book_name": complemented["book_name"],
            "chapter_title": complemented["chapter_title"],
            "provider": analysis["provider"],
            "model": analysis["model"],
            "quality_score": complemented["quality_score"],
            "characters": analysis["result"].get("characters", []),
        }
```

```python
# backend/app/interfaces/http/reading.py
class CharacterCalibrationRequest(BaseModel):
    keyword: str
    chapter_index: int = 0
    source_ids: list[int] | None = None
    model: str = "gpt-4.1-mini"


@router.post("/characters/calibrate")
async def calibrate_characters(
    payload: CharacterCalibrationRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.AI_RUN)),
):
    service = build_character_calibration_service()
    data = await service.calibrate(payload.model_dump(), actor_id=str(identity.user_id))
    return {"success": True, "code": "OK", "message": "character calibration completed", "data": data, "meta": {}, "trace_id": None}
```

```python
# backend/scripts/smoke_character_calibration.py
DEFAULT_KEYWORDS = ["捞尸人", "斗罗大陆"]
required_env = ["LLM_API_URL", "LLM_API_KEY", "LLM_MODEL"]
print(f"[character-calibration] requires env: {', '.join(required_env)}")
```

- [ ] **Step 4: Run tests and the calibration smoke**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_character_calibration_api.py -v`  
Expected: PASS.

Run: `.\.venv\Scripts\python.exe scripts\smoke_character_calibration.py`  
Expected: when `LLM_API_URL`, `LLM_API_KEY`, and `LLM_MODEL` are configured, prints canonical character rows for `捞尸人` and `斗罗大陆`; otherwise exits with a clear “missing provider env” message and non-zero status.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend/app/application/services/character_calibration_service.py docs/superpowers/reports/checkpoints/2026-07-09-real-source-task4.py`  
Expected: checkpoint file exists.

### Task 5: Wire the basic control-plane UI for import, search, complement, and calibration

**Files:**
- Modify: `frontend/src/api/modules/sources.ts`
- Create: `frontend/src/api/modules/reading.ts`
- Modify: `frontend/src/features/sources/SourceListPage.tsx`
- Create: `frontend/src/features/reading/ReadingWorkbenchPage.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/features/sources/SourceListPage.test.tsx`
- Create: `frontend/src/features/reading/ReadingWorkbenchPage.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

vi.mock('@/api/modules/reading', () => ({
  searchBooks: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [{ name: '捞尸人', sourceName: '测试源A', author: '作者A', bookUrl: 'https://a.example.com/book/1' }],
    meta: { keyword: '捞尸人' },
    trace_id: null,
  }),
}))

import { ReadingWorkbenchPage } from '@/features/reading/ReadingWorkbenchPage'

test('reading workbench shows search results for the smoke titles', async () => {
  render(<ReadingWorkbenchPage />)

  expect(await screen.findByText('捞尸人')).toBeInTheDocument()
  expect(await screen.findByText('测试源A')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- --run src/features/reading/ReadingWorkbenchPage.test.tsx src/features/sources/SourceListPage.test.tsx`  
Expected: FAIL because the reading API module and page do not exist.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/api/modules/reading.ts
import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface ReadingSearchRow {
  name: string
  author: string
  sourceName: string
  bookUrl: string
}

export async function searchBooks(keyword: string) {
  return apiClient.post<ReadingSearchRow[]>('/reading/search', { keyword }) as Promise<ApiEnvelope<ReadingSearchRow[]>>
}
```

```tsx
// frontend/src/features/reading/ReadingWorkbenchPage.tsx
export function ReadingWorkbenchPage() {
  const [rows, setRows] = useState<ReadingSearchRow[]>([])

  useEffect(() => {
    searchBooks('捞尸人').then((response) => setRows(response.data))
  }, [])

  return (
    <ConsoleLayout eyebrow="Reading" title="Real source workbench" description="导入书源后，直接做真实搜索、多源互补、质量选择与人物校准。">
      {rows.map((row) => (
        <article key={row.bookUrl}>
          <h3>{row.name}</h3>
          <p>{row.sourceName}</p>
        </article>
      ))}
    </ConsoleLayout>
  )
}
```

```tsx
// frontend/src/app/router.tsx
<Route path="/reading/workbench" element={<ReadingWorkbenchPage />} />
```

- [ ] **Step 4: Run frontend tests and build**

Run: `npm --prefix frontend run test -- --run src/features/reading/ReadingWorkbenchPage.test.tsx src/features/sources/SourceListPage.test.tsx`  
Expected: PASS.

Run: `npm --prefix frontend run build`  
Expected: build succeeds.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item frontend/src/features/reading/ReadingWorkbenchPage.tsx docs/superpowers/reports/checkpoints/2026-07-09-real-source-task5.tsx`  
Expected: checkpoint file exists.

## Self-review

### Spec coverage

- Real local source import from `测试源/shareBookSource.json`: covered by Task 1.
- Real search for `捞尸人` and `斗罗大陆`: covered by Task 2.
- Multi-source complement / correction / quality selection: covered by Task 3.
- Character calibration: covered by Task 4.
- Basic control-plane entry points: covered by Task 5.

### Placeholder scan

- No `TODO` / `TBD` placeholders remain.
- Every task has exact files, tests, commands, and checkpoint actions.

### Type consistency

- `SourceReadService.search_books()` is used consistently by `reading.py` and by the complement layer.
- `SourceComplementAppService.complement()` returns `quality_choice`, `quality_score`, `merged_from`, which match Task 3 API expectations.
- `CharacterCalibrationService.calibrate()` consumes complement output and returns `provider`, `model`, `characters`, which match Task 4 tests and API shape.

Plan complete and saved to `docs/superpowers/plans/2026-07-09-real-source-basic-runtime.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
