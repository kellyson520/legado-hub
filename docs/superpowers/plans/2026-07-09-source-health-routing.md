# Source Health Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-stage source health system that probes real book sources, classifies failure reasons, drives runtime routing for search/toc/content, and exposes an admin panel for health operations.

**Architecture:** Add an isolated source-health persistence layer, then implement probe/classifier/admin orchestration services on top of the existing `LegadoBookSourceFetcher`. Feed the resulting snapshots into a routing service used by `SourceReadService`, then expose the data through new HTTP endpoints, scheduler jobs, regression scripts, and a frontend control plane.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, SQLite, pytest, React 18, TypeScript, Vitest, existing Legado JS runtime/fetcher

---

> **Git note:** this working copy currently has no `.git`. Replace each “Commit” step with a filesystem checkpoint under `docs/superpowers/reports/checkpoints/`.

## File Structure

```text
backend/app/domain/entities/
├── source_health.py                           # source health snapshot / probe run dataclasses
backend/app/domain/repositories/
├── source_health_repo.py                      # persistence contract for snapshots and probe runs
├── source_repo.py                             # extend with mirror-update helper for book_sources
backend/app/application/services/
├── source_health_models.py                    # typed stage evidence / decision models
├── source_probe_service.py                    # runs search/toc/content probes against real sources
├── source_health_classifier_service.py        # maps probe evidence to health/failure/routing decisions
├── source_health_admin_service.py             # probe orchestration, persistence, mirror sync, manual actions
├── source_routing_service.py                  # search/toc/content routing and fallback logic
├── source_read_service.py                     # consume routing service and expose routing-aware reads
backend/app/infrastructure/persistence/sqlite/
├── schema.py                                  # SourceHealthSnapshotModel / SourceProbeRunModel
├── source_health_repo_impl.py                 # SQLite source health repository
├── source_repo_impl.py                        # mirror update helper for book_sources
backend/app/infrastructure/persistence/
├── factory.py                                 # builders for health repo/services/routing service
backend/app/interfaces/http/
├── source_health.py                           # admin health endpoints
├── reading.py                                 # routing_mode/include_health/fallback request fields
├── router.py                                  # include source_health router
backend/app/tasks/
├── scheduler.py                               # add source health probe job entrypoint
backend/scripts/
├── probe_source_health.py                     # batch probe CLI for real sources
├── search_real_books.py                       # print route decisions and health summaries
├── smoke_js_compat_sources.py                 # print classification results for JS-heavy sources
backend/tests/
├── test_source_health_repo.py
├── test_source_probe_service.py
├── test_source_health_classifier_service.py
├── test_source_health_admin_service.py
├── test_source_routing_service.py
├── test_api_source_health.py
├── test_source_health_scheduler.py
├── test_source_read_service.py
frontend/src/api/modules/
├── sourceHealth.ts                            # frontend API client for health endpoints
frontend/src/features/sources/
├── SourceHealthPage.tsx                       # health dashboard / table / actions
├── SourceHealthPage.test.tsx                  # vitest coverage for page rendering and actions
├── SourceListPage.tsx                         # add navigation entry to health control plane
frontend/src/app/
├── router.tsx                                 # register `/sources/health`
```

### Task 1: Create the source-health persistence foundation

**Files:**
- Create: `backend/app/domain/entities/source_health.py`
- Create: `backend/app/domain/repositories/source_health_repo.py`
- Modify: `backend/app/domain/repositories/source_repo.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/schema.py`
- Create: `backend/app/infrastructure/persistence/sqlite/source_health_repo_impl.py`
- Modify: `backend/app/infrastructure/persistence/sqlite/source_repo_impl.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Create: `backend/tests/test_source_health_repo.py`

- [ ] **Step 1: Write the failing repository test**

```python
from datetime import datetime, timezone


def test_source_health_repository_persists_snapshot_and_probe_history(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-repo.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
    from app.infrastructure.persistence.factory import build_source_health_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    repo = build_source_health_repository()

    snapshot = repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=7,
            source_name="起点读书限免+本章说",
            source_url="https://www.qidian.com",
            health_status="blocked",
            search_status="failed",
            toc_status="skipped",
            content_status="skipped",
            failure_reason="token_missing",
            decision_confidence="high",
            route_policy="skip",
            route_score=0.0,
            consecutive_failures=2,
            consecutive_successes=0,
            last_probe_at=datetime.now(timezone.utc),
            metadata={"keyword": "捞尸人"},
        )
    )

    repo.record_probe_run(
        SourceProbeRun(
            source_id=7,
            source_name="起点读书限免+本章说",
            probe_mode="full_chain",
            keyword="捞尸人",
            overall_status="blocked",
            failure_reason="token_missing",
            search_result={"request_preview": "https://www.qidian.com/search?token=undefined"},
            toc_result={},
            content_result={},
            summary={"hit_count": 0},
        )
    )

    loaded = repo.get_snapshot(7)
    rows, total = repo.list_snapshots(statuses=["blocked"], limit=10, offset=0)
    runs = repo.list_probe_runs(7, limit=5)

    assert snapshot.source_id == 7
    assert loaded is not None
    assert loaded.failure_reason == "token_missing"
    assert total == 1
    assert rows[0].route_policy == "skip"
    assert runs[0].overall_status == "blocked"
    assert runs[0].search_result["request_preview"].endswith("token=undefined")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_health_repo.py -v`
Expected: FAIL because `SourceHealthSnapshot`, `SourceProbeRun`, `SourceHealthRepository`, and `build_source_health_repository()` do not exist.

- [ ] **Step 3: Write the minimal persistence implementation**

```python
# backend/app/domain/entities/source_health.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SourceHealthSnapshot:
    source_id: int
    source_name: str
    source_url: str
    health_status: str = "unknown"
    search_status: str = "unknown"
    toc_status: str = "unknown"
    content_status: str = "unknown"
    failure_reason: str = ""
    decision_confidence: str = "low"
    route_policy: str = "probe_only"
    route_score: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_success_at: datetime | None = None
    last_probe_at: datetime | None = None
    next_probe_at: datetime | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SourceProbeRun:
    source_id: int
    source_name: str
    probe_mode: str
    keyword: str
    overall_status: str
    failure_reason: str
    id: str = field(default_factory=lambda: uuid4().hex)
    search_result: dict = field(default_factory=dict)
    toc_result: dict = field(default_factory=dict)
    content_result: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
```

```python
# backend/app/domain/repositories/source_health_repo.py
from abc import ABC, abstractmethod

from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun


class SourceHealthRepository(ABC):
    @abstractmethod
    def get_snapshot(self, source_id: int) -> SourceHealthSnapshot | None:
        raise NotImplementedError

    @abstractmethod
    def list_snapshots(
        self,
        statuses: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SourceHealthSnapshot], int]:
        raise NotImplementedError

    @abstractmethod
    def upsert_snapshot(self, snapshot: SourceHealthSnapshot) -> SourceHealthSnapshot:
        raise NotImplementedError

    @abstractmethod
    def record_probe_run(self, run: SourceProbeRun) -> SourceProbeRun:
        raise NotImplementedError

    @abstractmethod
    def list_probe_runs(self, source_id: int, limit: int = 20) -> list[SourceProbeRun]:
        raise NotImplementedError
```

```python
# append to backend/app/infrastructure/persistence/sqlite/schema.py
class SourceHealthSnapshotModel(Base):
    __tablename__ = "source_health_snapshots"

    source_id = Column(Integer, primary_key=True)
    source_name = Column(String, nullable=False, default="")
    source_url = Column(Text, nullable=False, default="")
    health_status = Column(String, nullable=False, default="unknown", index=True)
    search_status = Column(String, nullable=False, default="unknown")
    toc_status = Column(String, nullable=False, default="unknown")
    content_status = Column(String, nullable=False, default="unknown")
    failure_reason = Column(String, nullable=False, default="")
    decision_confidence = Column(String, nullable=False, default="low")
    route_policy = Column(String, nullable=False, default="probe_only")
    route_score = Column(String, nullable=False, default="0")
    consecutive_failures = Column(Integer, nullable=False, default=0)
    consecutive_successes = Column(Integer, nullable=False, default=0)
    last_success_at = Column(DateTime, nullable=True)
    last_probe_at = Column(DateTime, nullable=True)
    next_probe_at = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")


class SourceProbeRunModel(Base):
    __tablename__ = "source_probe_runs"

    id = Column(String, primary_key=True)
    source_id = Column(Integer, nullable=False, index=True)
    source_name = Column(String, nullable=False, default="")
    probe_mode = Column(String, nullable=False, default="search_only")
    keyword = Column(String, nullable=False, default="")
    overall_status = Column(String, nullable=False, default="unknown", index=True)
    failure_reason = Column(String, nullable=False, default="")
    search_result = Column(Text, nullable=False, default="{}")
    toc_result = Column(Text, nullable=False, default="{}")
    content_result = Column(Text, nullable=False, default="{}")
    summary = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False)
```

```python
# backend/app/infrastructure/persistence/sqlite/source_health_repo_impl.py
import json

from app.database import SessionLocal
from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun
from app.domain.repositories.source_health_repo import SourceHealthRepository
from app.infrastructure.persistence.sqlite.schema import SourceHealthSnapshotModel, SourceProbeRunModel


class SQLiteSourceHealthRepository(SourceHealthRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    def _snapshot_to_entity(self, model: SourceHealthSnapshotModel) -> SourceHealthSnapshot:
        return SourceHealthSnapshot(
            source_id=model.source_id,
            source_name=model.source_name,
            source_url=model.source_url,
            health_status=model.health_status,
            search_status=model.search_status,
            toc_status=model.toc_status,
            content_status=model.content_status,
            failure_reason=model.failure_reason,
            decision_confidence=model.decision_confidence,
            route_policy=model.route_policy,
            route_score=float(model.route_score or 0),
            consecutive_failures=model.consecutive_failures,
            consecutive_successes=model.consecutive_successes,
            last_success_at=model.last_success_at,
            last_probe_at=model.last_probe_at,
            next_probe_at=model.next_probe_at,
            metadata=json.loads(model.metadata_json or "{}"),
        )

    def _run_to_entity(self, model: SourceProbeRunModel) -> SourceProbeRun:
        return SourceProbeRun(
            id=model.id,
            source_id=model.source_id,
            source_name=model.source_name,
            probe_mode=model.probe_mode,
            keyword=model.keyword,
            overall_status=model.overall_status,
            failure_reason=model.failure_reason,
            search_result=json.loads(model.search_result or "{}"),
            toc_result=json.loads(model.toc_result or "{}"),
            content_result=json.loads(model.content_result or "{}"),
            summary=json.loads(model.summary or "{}"),
            created_at=model.created_at,
        )

    def get_snapshot(self, source_id: int) -> SourceHealthSnapshot | None:
        db = self._db()
        try:
            row = db.query(SourceHealthSnapshotModel).filter(SourceHealthSnapshotModel.source_id == source_id).first()
            return self._snapshot_to_entity(row) if row else None
        finally:
            self._close(db)

    def list_snapshots(self, statuses=None, limit: int = 50, offset: int = 0):
        db = self._db()
        try:
            query = db.query(SourceHealthSnapshotModel).order_by(SourceHealthSnapshotModel.source_id.asc())
            if statuses:
                query = query.filter(SourceHealthSnapshotModel.health_status.in_(statuses))
            total = query.count()
            rows = query.offset(offset).limit(limit).all()
            return [self._snapshot_to_entity(row) for row in rows], total
        finally:
            self._close(db)

    def upsert_snapshot(self, snapshot: SourceHealthSnapshot) -> SourceHealthSnapshot:
        db = self._db()
        try:
            row = db.query(SourceHealthSnapshotModel).filter(SourceHealthSnapshotModel.source_id == snapshot.source_id).first()
            if row is None:
                row = SourceHealthSnapshotModel(source_id=snapshot.source_id)
                db.add(row)
            row.source_name = snapshot.source_name
            row.source_url = snapshot.source_url
            row.health_status = snapshot.health_status
            row.search_status = snapshot.search_status
            row.toc_status = snapshot.toc_status
            row.content_status = snapshot.content_status
            row.failure_reason = snapshot.failure_reason
            row.decision_confidence = snapshot.decision_confidence
            row.route_policy = snapshot.route_policy
            row.route_score = str(snapshot.route_score)
            row.consecutive_failures = snapshot.consecutive_failures
            row.consecutive_successes = snapshot.consecutive_successes
            row.last_success_at = snapshot.last_success_at
            row.last_probe_at = snapshot.last_probe_at
            row.next_probe_at = snapshot.next_probe_at
            row.metadata_json = json.dumps(snapshot.metadata, ensure_ascii=False)
            db.commit()
            db.refresh(row)
            return self._snapshot_to_entity(row)
        finally:
            self._close(db)

    def record_probe_run(self, run: SourceProbeRun) -> SourceProbeRun:
        db = self._db()
        try:
            row = SourceProbeRunModel(
                id=run.id,
                source_id=run.source_id,
                source_name=run.source_name,
                probe_mode=run.probe_mode,
                keyword=run.keyword,
                overall_status=run.overall_status,
                failure_reason=run.failure_reason,
                search_result=json.dumps(run.search_result, ensure_ascii=False),
                toc_result=json.dumps(run.toc_result, ensure_ascii=False),
                content_result=json.dumps(run.content_result, ensure_ascii=False),
                summary=json.dumps(run.summary, ensure_ascii=False),
                created_at=run.created_at,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._run_to_entity(row)
        finally:
            self._close(db)

    def list_probe_runs(self, source_id: int, limit: int = 20) -> list[SourceProbeRun]:
        db = self._db()
        try:
            rows = (
                db.query(SourceProbeRunModel)
                .filter(SourceProbeRunModel.source_id == source_id)
                .order_by(SourceProbeRunModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._run_to_entity(row) for row in rows]
        finally:
            self._close(db)
```

```python
# add to backend/app/domain/repositories/source_repo.py
    async def update_book_source_health_fields(
        self,
        source_id: int,
        source_status: str,
        error_msg: str,
        last_check_time,
    ) -> dict:
        raise NotImplementedError
```

```python
# add to backend/app/infrastructure/persistence/sqlite/source_repo_impl.py
from datetime import datetime

    async def update_book_source_health_fields(
        self,
        source_id: int,
        source_status: str,
        error_msg: str,
        last_check_time: datetime,
    ) -> dict:
        db = SessionLocal()
        try:
            model = db.query(BookSourceModel).filter(BookSourceModel.id == source_id).first()
            model.sourceStatus = source_status
            model.errorMsg = error_msg
            model.lastCheckTime = last_check_time
            db.commit()
            db.refresh(model)
            return self._book_to_dict(model)
        finally:
            db.close()
```

```python
# add to backend/app/infrastructure/persistence/factory.py
from app.infrastructure.persistence.sqlite.source_health_repo_impl import SQLiteSourceHealthRepository


def build_source_health_repository() -> SQLiteSourceHealthRepository:
    bootstrap_sqlite()
    return SQLiteSourceHealthRepository()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_health_repo.py -v`
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\infrastructure\persistence\sqlite\source_health_repo_impl.py docs\superpowers\reports\checkpoints\2026-07-09-source-health-task1-repo.py`
Expected: checkpoint file exists.

### Task 2: Add probe evidence models and the health classifier

**Files:**
- Create: `backend/app/application/services/source_health_models.py`
- Create: `backend/app/application/services/source_probe_service.py`
- Create: `backend/app/application/services/source_health_classifier_service.py`
- Create: `backend/tests/test_source_probe_service.py`
- Create: `backend/tests/test_source_health_classifier_service.py`

- [ ] **Step 1: Write the failing probe/classifier tests**

```python
from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult


def test_classifier_marks_token_missing_as_blocked_and_skipped():
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService

    evidence = SourceProbeEvidence(
        source_id=4,
        source_name="起点读书限免+本章说",
        source_url="https://www.qidian.com",
        probe_mode="search_only",
        keyword="捞尸人",
        search=StageProbeResult(
            stage="search",
            status="failed",
            request_preview="https://www.qidian.com/search?token=undefined",
            detail={"js_exec_status": "ok"},
        ),
        toc=StageProbeResult(stage="toc", status="skipped"),
        content=StageProbeResult(stage="content", status="skipped"),
    )

    decision = SourceHealthClassifierService().classify(evidence)

    assert decision.health_status == "blocked"
    assert decision.failure_reason == "token_missing"
    assert decision.route_policy == "skip"


import pytest


class FakeFetcher:
    async def search(self, source, keyword, page=1):
        return [{"name": keyword, "author": "唐家三少", "bookUrl": source["bookSourceUrl"] + "/book/1"}]

    async def get_toc(self, source, book_url):
        return [{"title": "第一章", "url": book_url + "/1"}]

    async def get_content(self, source, chapter_url):
        raise RuntimeError("Unexpected token '<' while decoding JSON payload")


@pytest.mark.asyncio
async def test_probe_service_collects_three_stage_evidence_and_content_failure():
    from app.application.services.source_probe_service import SourceProbeService

    source = {
        "id": 109,
        "bookSourceName": "读书阁③",
        "bookSourceUrl": "https://www.dushuge.example",
    }

    probe = await SourceProbeService(fetcher=FakeFetcher()).probe_source(
        source=source,
        keyword_samples=["斗罗大陆"],
        probe_mode="full_chain",
    )

    assert probe.search.status == "ok"
    assert probe.toc.status == "ok"
    assert probe.content.status == "failed"
    assert "Unexpected token '<'" in probe.content.error_message
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_probe_service.py tests\test_source_health_classifier_service.py -v`
Expected: FAIL because the probe models, probe service, and classifier do not exist.

- [ ] **Step 3: Write the minimal probe and classifier implementation**

```python
# backend/app/application/services/source_health_models.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StageProbeResult:
    stage: str
    status: str = "unknown"
    elapsed_ms: int = 0
    request_preview: str = ""
    response_kind: str = ""
    hit_count: int = 0
    sample_title: str = ""
    error_message: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class SourceProbeEvidence:
    source_id: int
    source_name: str
    source_url: str
    probe_mode: str
    keyword: str
    search: StageProbeResult
    toc: StageProbeResult
    content: StageProbeResult


@dataclass
class SourceHealthDecision:
    source_id: int
    source_name: str
    source_url: str
    health_status: str
    search_status: str
    toc_status: str
    content_status: str
    failure_reason: str
    decision_confidence: str
    route_policy: str
    route_score: float
    metadata: dict = field(default_factory=dict)
```

```python
# backend/app/application/services/source_probe_service.py
from __future__ import annotations

import time

from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult


class SourceProbeService:
    def __init__(self, fetcher):
        self._fetcher = fetcher

    async def probe_source(
        self,
        source: dict,
        keyword_samples: list[str],
        probe_mode: str = "full_chain",
    ) -> SourceProbeEvidence:
        keyword = keyword_samples[0]

        search_started = time.perf_counter()
        try:
            found = await self._fetcher.search(source, keyword, page=1)
            search = StageProbeResult(
                stage="search",
                status="ok" if found else "failed",
                elapsed_ms=int((time.perf_counter() - search_started) * 1000),
                hit_count=len(found),
                sample_title=found[0].get("name", "") if found else "",
                detail={"top_hit": found[0] if found else {}},
            )
        except Exception as exc:
            found = []
            search = StageProbeResult(
                stage="search",
                status="failed",
                elapsed_ms=int((time.perf_counter() - search_started) * 1000),
                error_message=str(exc),
            )

        toc = StageProbeResult(stage="toc", status="skipped")
        content = StageProbeResult(stage="content", status="skipped")

        if probe_mode == "full_chain" and found:
            book_url = found[0].get("bookUrl", "")
            toc_started = time.perf_counter()
            try:
                chapters = await self._fetcher.get_toc(source, book_url)
                toc = StageProbeResult(
                    stage="toc",
                    status="ok" if chapters else "failed",
                    elapsed_ms=int((time.perf_counter() - toc_started) * 1000),
                    hit_count=len(chapters),
                    sample_title=chapters[0].get("title", "") if chapters else "",
                    detail={"first_chapter": chapters[0] if chapters else {}},
                )
            except Exception as exc:
                chapters = []
                toc = StageProbeResult(
                    stage="toc",
                    status="failed",
                    elapsed_ms=int((time.perf_counter() - toc_started) * 1000),
                    error_message=str(exc),
                )

            if chapters:
                content_started = time.perf_counter()
                try:
                    payload = await self._fetcher.get_content(source, chapters[0]["url"])
                    body = payload.get("content", "")
                    content = StageProbeResult(
                        stage="content",
                        status="ok" if body else "failed",
                        elapsed_ms=int((time.perf_counter() - content_started) * 1000),
                        sample_title=payload.get("title", ""),
                        detail={"content_length": len(body)},
                    )
                except Exception as exc:
                    content = StageProbeResult(
                        stage="content",
                        status="failed",
                        elapsed_ms=int((time.perf_counter() - content_started) * 1000),
                        error_message=str(exc),
                    )

        return SourceProbeEvidence(
            source_id=source["id"],
            source_name=source.get("bookSourceName", ""),
            source_url=source.get("bookSourceUrl", ""),
            probe_mode=probe_mode,
            keyword=keyword,
            search=search,
            toc=toc,
            content=content,
        )
```

```python
# backend/app/application/services/source_health_classifier_service.py
from __future__ import annotations

from app.application.services.source_health_models import SourceHealthDecision, SourceProbeEvidence


class SourceHealthClassifierService:
    def classify(self, evidence: SourceProbeEvidence) -> SourceHealthDecision:
        failure_reason = self._failure_reason(evidence)
        health_status = self._health_status(evidence, failure_reason)
        route_policy = "allow"
        route_score = 100.0
        if health_status == "degraded":
            route_policy = "deprioritize"
            route_score = 45.0
        elif health_status in {"blocked", "dead"}:
            route_policy = "skip"
            route_score = 0.0
        elif health_status == "unknown":
            route_policy = "probe_only"
            route_score = 10.0

        return SourceHealthDecision(
            source_id=evidence.source_id,
            source_name=evidence.source_name,
            source_url=evidence.source_url,
            health_status=health_status,
            search_status=evidence.search.status,
            toc_status=evidence.toc.status,
            content_status=evidence.content.status,
            failure_reason=failure_reason,
            decision_confidence=self._confidence(evidence, failure_reason),
            route_policy=route_policy,
            route_score=route_score,
            metadata={
                "keyword": evidence.keyword,
                "next_probe_after_minutes": self._next_probe_minutes(failure_reason),
            },
        )

    def _failure_reason(self, evidence: SourceProbeEvidence) -> str:
        haystacks = [
            evidence.search.request_preview,
            evidence.search.error_message,
            evidence.content.error_message,
            str(evidence.search.detail),
            str(evidence.content.detail),
        ]
        merged = " ".join(item for item in haystacks if item)
        lowered = merged.lower()

        if "token=undefined" in lowered:
            return "token_missing"
        if "is not defined" in lowered:
            return "helper_missing"
        if "unexpected token '<'" in lowered:
            return "upstream_changed"
        if "10054" in lowered or "connection reset" in lowered:
            return "waf_blocked"
        if "timeout" in lowered:
            return "timeout"
        if evidence.search.status == "failed" and evidence.search.hit_count == 0 and not merged:
            return "keyword_no_result"
        if evidence.search.status == "ok" and evidence.toc.status == "ok" and evidence.content.status == "failed":
            return "parse_empty"
        return "unknown_error" if any(stage.status == "failed" for stage in [evidence.search, evidence.toc, evidence.content]) else ""

    def _health_status(self, evidence: SourceProbeEvidence, failure_reason: str) -> str:
        if evidence.search.status == "ok" and evidence.toc.status in {"ok", "skipped"} and evidence.content.status in {"ok", "skipped"}:
            return "healthy"
        if failure_reason in {"token_missing", "auth_required", "cookie_required", "waf_blocked", "timeout"}:
            return "blocked"
        if failure_reason in {"helper_missing", "upstream_changed", "invalid_source_rule", "deprecated_source"}:
            return "dead"
        if evidence.search.status == "ok" and (evidence.toc.status == "failed" or evidence.content.status == "failed"):
            return "degraded"
        return "unknown"

    def _confidence(self, evidence: SourceProbeEvidence, failure_reason: str) -> str:
        if failure_reason in {"token_missing", "helper_missing", "upstream_changed", "waf_blocked"}:
            return "high"
        if failure_reason in {"timeout", "parse_empty", "keyword_no_result"}:
            return "medium"
        return "low"

    def _next_probe_minutes(self, failure_reason: str) -> int:
        if failure_reason in {"timeout", "waf_blocked"}:
            return 60
        if failure_reason in {"token_missing", "auth_required"}:
            return 360
        if failure_reason in {"helper_missing", "upstream_changed", "deprecated_source"}:
            return 1440
        return 15
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_probe_service.py tests\test_source_health_classifier_service.py -v`
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\application\services\source_health_classifier_service.py docs\superpowers\reports\checkpoints\2026-07-09-source-health-task2-classifier.py`
Expected: checkpoint file exists.

### Task 3: Add admin orchestration, snapshot mirroring, and manual actions

**Files:**
- Create: `backend/app/application/services/source_health_admin_service.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Create: `backend/tests/test_source_health_admin_service.py`

- [ ] **Step 1: Write the failing admin-service tests**

```python
import pytest


class FakeProbeService:
    async def probe_source(self, source, keyword_samples, probe_mode="full_chain"):
        from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult

        return SourceProbeEvidence(
            source_id=source["id"],
            source_name=source["bookSourceName"],
            source_url=source["bookSourceUrl"],
            probe_mode=probe_mode,
            keyword=keyword_samples[0],
            search=StageProbeResult(stage="search", status="failed", request_preview="https://www.qidian.com/search?token=undefined"),
            toc=StageProbeResult(stage="toc", status="skipped"),
            content=StageProbeResult(stage="content", status="skipped"),
        )


@pytest.mark.asyncio
async def test_admin_service_persists_snapshot_and_mirrors_book_source_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-admin.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.application.services.source_health_classifier_service import SourceHealthClassifierService
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    created = await source_repo.create_book_source(
        {
            "bookSourceName": "起点读书限免+本章说",
            "bookSourceUrl": "https://www.qidian.com",
            "enabled": True,
        },
        actor_id=1,
    )

    service = SourceHealthAdminService(
        source_repo=source_repo,
        health_repo=health_repo,
        probe_service=FakeProbeService(),
        classifier=SourceHealthClassifierService(),
    )

    result = await service.probe_book_source(created["id"], keyword_samples=["捞尸人"], probe_mode="full_chain")
    source_row = (await source_repo.list_book_sources_full(ids=[created["id"]]))[0]
    snapshot = health_repo.get_snapshot(created["id"])

    assert result["snapshot"]["health_status"] == "blocked"
    assert source_row["sourceStatus"] == "blocked"
    assert "token_missing" in (source_row["errorMsg"] or "")
    assert snapshot is not None
    assert snapshot.route_policy == "skip"


@pytest.mark.asyncio
async def test_admin_service_recover_source_resets_blocked_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-recover.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.source_health_admin_service import SourceHealthAdminService
    from app.domain.entities.source_health import SourceHealthSnapshot
    from app.infrastructure.persistence.factory import build_source_health_repository, build_source_repository
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite

    bootstrap_sqlite()
    source_repo = build_source_repository()
    health_repo = build_source_health_repository()
    created = await source_repo.create_book_source(
        {"bookSourceName": "八叉书库", "bookSourceUrl": "https://www.8cha.example", "enabled": True},
        actor_id=1,
    )
    health_repo.upsert_snapshot(
        SourceHealthSnapshot(
            source_id=created["id"],
            source_name=created["bookSourceName"],
            source_url=created["bookSourceUrl"],
            health_status="blocked",
            failure_reason="waf_blocked",
            route_policy="skip",
        )
    )

    service = SourceHealthAdminService(source_repo=source_repo, health_repo=health_repo, probe_service=None, classifier=None)
    result = await service.recover_source(created["id"])

    assert result["health_status"] == "unknown"
    assert result["route_policy"] == "probe_only"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_health_admin_service.py -v`
Expected: FAIL because `SourceHealthAdminService` and its orchestration methods do not exist.

- [ ] **Step 3: Write the minimal admin orchestration implementation**

```python
# backend/app/application/services/source_health_admin_service.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun


class SourceHealthAdminService:
    def __init__(self, source_repo, health_repo, probe_service, classifier):
        self._source_repo = source_repo
        self._health_repo = health_repo
        self._probe_service = probe_service
        self._classifier = classifier

    async def list_book_source_health(self, page: int = 1, page_size: int = 20, statuses: list[str] | None = None) -> dict:
        rows, total = self._health_repo.list_snapshots(statuses=statuses, limit=page_size, offset=(page - 1) * page_size)
        data = [self._snapshot_to_dict(item) for item in rows]
        return {"items": data, "meta": {"page": page, "page_size": page_size, "total": total}}

    async def get_book_source_health(self, source_id: int) -> dict:
        snapshot = self._health_repo.get_snapshot(source_id)
        runs = self._health_repo.list_probe_runs(source_id, limit=10)
        return {
            "snapshot": self._snapshot_to_dict(snapshot) if snapshot else None,
            "runs": [self._run_to_dict(run) for run in runs],
        }

    async def probe_book_source(self, source_id: int, keyword_samples: list[str], probe_mode: str = "full_chain") -> dict:
        source = (await self._source_repo.list_book_sources_full(ids=[source_id]))[0]
        evidence = await self._probe_service.probe_source(source, keyword_samples=keyword_samples, probe_mode=probe_mode)
        decision = self._classifier.classify(evidence)
        now = datetime.now(timezone.utc)
        previous = self._health_repo.get_snapshot(source_id)
        consecutive_failures = 0 if decision.health_status == "healthy" else ((previous.consecutive_failures if previous else 0) + 1)
        consecutive_successes = ((previous.consecutive_successes if previous and decision.health_status == "healthy" else 0) + 1) if decision.health_status == "healthy" else 0
        snapshot = self._health_repo.upsert_snapshot(
            SourceHealthSnapshot(
                source_id=source_id,
                source_name=source["bookSourceName"],
                source_url=source["bookSourceUrl"],
                health_status=decision.health_status,
                search_status=decision.search_status,
                toc_status=decision.toc_status,
                content_status=decision.content_status,
                failure_reason=decision.failure_reason,
                decision_confidence=decision.decision_confidence,
                route_policy=decision.route_policy,
                route_score=decision.route_score,
                consecutive_failures=consecutive_failures,
                consecutive_successes=consecutive_successes,
                last_success_at=now if decision.health_status == "healthy" else (previous.last_success_at if previous else None),
                last_probe_at=now,
                next_probe_at=now + timedelta(minutes=decision.metadata.get("next_probe_after_minutes", 15)),
                metadata=decision.metadata,
            )
        )
        self._health_repo.record_probe_run(
            SourceProbeRun(
                source_id=source_id,
                source_name=source["bookSourceName"],
                probe_mode=probe_mode,
                keyword=evidence.keyword,
                overall_status=decision.health_status,
                failure_reason=decision.failure_reason,
                search_result=evidence.search.__dict__,
                toc_result=evidence.toc.__dict__,
                content_result=evidence.content.__dict__,
                summary={"route_policy": decision.route_policy, "route_score": decision.route_score},
            )
        )
        await self._source_repo.update_book_source_health_fields(
            source_id=source_id,
            source_status=decision.health_status,
            error_msg=f"{decision.failure_reason}:{decision.decision_confidence}" if decision.failure_reason else "",
            last_check_time=now,
        )
        return {"snapshot": self._snapshot_to_dict(snapshot), "decision": decision.metadata}

    async def probe_book_sources(self, source_ids: list[int], keyword_samples: list[str], probe_mode: str = "full_chain") -> dict:
        results = []
        for source_id in source_ids:
            results.append(await self.probe_book_source(source_id, keyword_samples=keyword_samples, probe_mode=probe_mode))
        return {"results": results, "total": len(results)}

    async def recover_source(self, source_id: int) -> dict:
        source = (await self._source_repo.list_book_sources_full(ids=[source_id]))[0]
        snapshot = self._health_repo.upsert_snapshot(
            SourceHealthSnapshot(
                source_id=source_id,
                source_name=source["bookSourceName"],
                source_url=source["bookSourceUrl"],
                health_status="unknown",
                search_status="unknown",
                toc_status="unknown",
                content_status="unknown",
                route_policy="probe_only",
                failure_reason="",
                decision_confidence="low",
            )
        )
        await self._source_repo.update_book_source_health_fields(
            source_id=source_id,
            source_status="unknown",
            error_msg="",
            last_check_time=datetime.now(timezone.utc),
        )
        return self._snapshot_to_dict(snapshot)

    async def quarantine_source(self, source_id: int, note: str = "manual_quarantine") -> dict:
        source = (await self._source_repo.list_book_sources_full(ids=[source_id]))[0]
        snapshot = self._health_repo.upsert_snapshot(
            SourceHealthSnapshot(
                source_id=source_id,
                source_name=source["bookSourceName"],
                source_url=source["bookSourceUrl"],
                health_status="blocked",
                search_status="failed",
                toc_status="skipped",
                content_status="skipped",
                failure_reason=note,
                decision_confidence="high",
                route_policy="skip",
            )
        )
        await self._source_repo.update_book_source_health_fields(
            source_id=source_id,
            source_status="blocked",
            error_msg=note,
            last_check_time=datetime.now(timezone.utc),
        )
        return self._snapshot_to_dict(snapshot)

    @staticmethod
    def _snapshot_to_dict(snapshot):
        return {
            "source_id": snapshot.source_id,
            "source_name": snapshot.source_name,
            "source_url": snapshot.source_url,
            "health_status": snapshot.health_status,
            "search_status": snapshot.search_status,
            "toc_status": snapshot.toc_status,
            "content_status": snapshot.content_status,
            "failure_reason": snapshot.failure_reason,
            "decision_confidence": snapshot.decision_confidence,
            "route_policy": snapshot.route_policy,
            "route_score": snapshot.route_score,
            "last_probe_at": snapshot.last_probe_at.isoformat() if snapshot.last_probe_at else None,
            "next_probe_at": snapshot.next_probe_at.isoformat() if snapshot.next_probe_at else None,
            "metadata": snapshot.metadata,
        }

    @staticmethod
    def _run_to_dict(run):
        return {
            "id": run.id,
            "source_id": run.source_id,
            "keyword": run.keyword,
            "overall_status": run.overall_status,
            "failure_reason": run.failure_reason,
            "search_result": run.search_result,
            "toc_result": run.toc_result,
            "content_result": run.content_result,
            "summary": run.summary,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
```

```python
# add to backend/app/infrastructure/persistence/factory.py
from app.application.services.source_health_admin_service import SourceHealthAdminService
from app.application.services.source_health_classifier_service import SourceHealthClassifierService
from app.application.services.source_probe_service import SourceProbeService


def build_source_probe_service() -> SourceProbeService:
    return SourceProbeService(fetcher=LegadoBookSourceFetcher())


def build_source_health_classifier_service() -> SourceHealthClassifierService:
    return SourceHealthClassifierService()


def build_source_health_admin_service() -> SourceHealthAdminService:
    return SourceHealthAdminService(
        source_repo=build_source_repository(),
        health_repo=build_source_health_repository(),
        probe_service=build_source_probe_service(),
        classifier=build_source_health_classifier_service(),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_health_admin_service.py -v`
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\application\services\source_health_admin_service.py docs\superpowers\reports\checkpoints\2026-07-09-source-health-task3-admin.py`
Expected: checkpoint file exists.

### Task 4: Add search-stage routing and health-aware search results

**Files:**
- Create: `backend/app/application/services/source_routing_service.py`
- Modify: `backend/app/application/services/source_read_service.py`
- Modify: `backend/app/interfaces/http/reading.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Create: `backend/tests/test_source_routing_service.py`
- Modify: `backend/tests/test_source_read_service.py`

- [ ] **Step 1: Write the failing routing tests**

```python
from app.domain.entities.source_health import SourceHealthSnapshot


def test_routing_service_skips_blocked_and_prefers_plain_healthy_sources():
    from app.application.services.source_routing_service import SourceRoutingService

    sources = [
        {"id": 1, "bookSourceName": "Plain Healthy", "bookSourceUrl": "https://a.example.com", "searchUrl": "https://a.example.com/search?key={{key}}"},
        {"id": 2, "bookSourceName": "JS Blocked", "bookSourceUrl": "https://b.example.com", "searchUrl": "@js:return 'https://b.example.com'"},
        {"id": 3, "bookSourceName": "JS Degraded", "bookSourceUrl": "https://c.example.com", "searchUrl": "@js:return 'https://c.example.com'"},
    ]
    snapshots = {
        1: SourceHealthSnapshot(source_id=1, source_name="Plain Healthy", source_url="https://a.example.com", health_status="healthy", route_policy="allow", route_score=100),
        2: SourceHealthSnapshot(source_id=2, source_name="JS Blocked", source_url="https://b.example.com", health_status="blocked", failure_reason="token_missing", route_policy="skip", route_score=0),
        3: SourceHealthSnapshot(source_id=3, source_name="JS Degraded", source_url="https://c.example.com", health_status="degraded", failure_reason="upstream_changed", route_policy="deprioritize", route_score=40),
    }

    ranked = SourceRoutingService().rank_search_sources(sources, snapshots, routing_mode="auto")

    assert [item["source"]["id"] for item in ranked] == [1, 3]
    assert ranked[0]["decision"]["route_decision"] == "allow"
    assert ranked[1]["decision"]["route_decision"] == "deprioritize"
```

```python
import pytest


@pytest.mark.asyncio
async def test_source_read_service_returns_route_summary_and_health_fields():
    from app.application.services.source_read_service import SourceReadService

    class Repo:
        async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
            return [
                {"id": 1, "bookSourceName": "Healthy", "bookSourceUrl": "https://a.example.com", "enabled": True, "searchUrl": "https://a.example.com/search?key={{key}}"},
                {"id": 2, "bookSourceName": "Blocked", "bookSourceUrl": "https://b.example.com", "enabled": True, "searchUrl": "@js:return 'https://b.example.com'"},
            ]

    class Fetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "author": "唐家三少", "bookUrl": source["bookSourceUrl"] + "/book/1"}]

    class RoutingService:
        def rank_search_sources(self, sources, snapshots, routing_mode="auto"):
            return [
                {
                    "source": sources[0],
                    "decision": {"route_decision": "allow", "health_status": "healthy", "failure_reason": "", "route_score": 100},
                }
            ]

        def snapshot_map(self, source_ids):
            return {1: None, 2: None}

    service = SourceReadService(repo=Repo(), fetcher=Fetcher(), routing_service=RoutingService())
    result = await service.search_books(keyword="斗罗大陆", include_health=True, routing_mode="auto")

    assert result["items"][0]["health_status"] == "healthy"
    assert result["route_summary"]["selected_source_ids"] == [1]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_routing_service.py tests\test_source_read_service.py -v`
Expected: FAIL because the routing service does not exist and `SourceReadService.search_books()` does not expose routing metadata.

- [ ] **Step 3: Write the minimal search routing implementation**

```python
# backend/app/application/services/source_routing_service.py
from __future__ import annotations


class SourceRoutingService:
    def __init__(self, health_repo=None):
        self._health_repo = health_repo

    def snapshot_map(self, source_ids: list[int]) -> dict[int, object | None]:
        if self._health_repo is None:
            return {source_id: None for source_id in source_ids}
        return {source_id: self._health_repo.get_snapshot(source_id) for source_id in source_ids}

    def rank_search_sources(self, sources: list[dict], snapshots: dict[int, object | None], routing_mode: str = "auto") -> list[dict]:
        ranked = []
        for source in sources:
            snapshot = snapshots.get(source["id"])
            health_status = getattr(snapshot, "health_status", "unknown") if snapshot else "unknown"
            failure_reason = getattr(snapshot, "failure_reason", "") if snapshot else ""
            route_policy = getattr(snapshot, "route_policy", "probe_only") if snapshot else "probe_only"
            route_score = float(getattr(snapshot, "route_score", 10.0) if snapshot else 10.0)

            if routing_mode == "auto" and health_status in {"dead", "blocked", "disabled"}:
                continue

            is_js = str(source.get("searchUrl", "") or "").strip().startswith("@js:")
            score = route_score
            if health_status == "healthy":
                score += 100
            elif health_status == "degraded":
                score += 25
            elif health_status == "unknown":
                score += 5
            if not is_js:
                score += 20

            decision = {
                "health_status": health_status,
                "failure_reason": failure_reason,
                "route_decision": "allow" if health_status == "healthy" else ("deprioritize" if health_status == "degraded" else route_policy),
                "route_score": score,
            }
            ranked.append({"source": source, "decision": decision})

        ranked.sort(key=lambda item: item["decision"]["route_score"], reverse=True)
        return ranked
```

```python
# key updates in backend/app/application/services/source_read_service.py
class SourceReadService:
    def __init__(self, repo, fetcher, routing_service=None):
        self._repo = repo
        self._fetcher = fetcher
        self._routing_service = routing_service

    async def search_books(
        self,
        keyword: str,
        source_ids: list[int] | None = None,
        limit_per_source: int = 3,
        author_hint: str | None = None,
        routing_mode: str = "auto",
        include_health: bool = False,
    ) -> dict:
        sources = await self._repo.list_book_sources_full(enabled_only=True, ids=source_ids)
        ranked_sources = [{"source": source, "decision": {"health_status": "unknown", "failure_reason": "", "route_decision": "probe_only", "route_score": 0}} for source in sources]
        if self._routing_service is not None:
            snapshot_map = self._routing_service.snapshot_map([source["id"] for source in sources])
            ranked_sources = self._routing_service.rank_search_sources(sources, snapshot_map, routing_mode=routing_mode)

        items: list[dict] = []
        selected_source_ids: list[int] = []
        for routed in ranked_sources:
            source = routed["source"]
            decision = routed["decision"]
            found = await self._fetcher.search(source, keyword, page=1)
            selected_source_ids.append(source["id"])
            ranked = sorted(
                found,
                key=lambda book: self._score_book_candidate(keyword, author_hint, book),
                reverse=True,
            )
            for book in ranked[:limit_per_source]:
                item = {
                    "source_id": source["id"],
                    "name": book.get("name", ""),
                    "author": book.get("author", ""),
                    "bookUrl": book.get("bookUrl", ""),
                    "sourceName": source["bookSourceName"],
                    "sourceUrl": source["bookSourceUrl"],
                }
                if include_health:
                    item.update(
                        {
                            "health_status": decision["health_status"],
                            "failure_reason": decision["failure_reason"],
                            "route_decision": decision["route_decision"],
                            "route_score": decision["route_score"],
                        }
                    )
                items.append(item)

        return {
            "keyword": keyword,
            "items": items,
            "route_summary": {
                "selected_source_ids": selected_source_ids,
                "routing_mode": routing_mode,
                "include_health": include_health,
            },
        }
```

```python
# updates in backend/app/interfaces/http/reading.py
class ReadingSearchRequest(BaseModel):
    keyword: str
    source_ids: list[int] | None = None
    limit_per_source: int = 3
    author_hint: str | None = None
    routing_mode: str = "auto"
    include_health: bool = False


@router.post("/search")
async def search_books(payload: ReadingSearchRequest, _=Depends(require_permission(Permission.BOOK_SOURCES_READ))):
    service = build_source_read_service()
    data = await service.search_books(
        payload.keyword,
        payload.source_ids,
        payload.limit_per_source,
        payload.author_hint,
        payload.routing_mode,
        payload.include_health,
    )
    return {
        "success": True,
        "code": "OK",
        "message": "search completed",
        "data": data["items"],
        "meta": data["route_summary"],
        "trace_id": None,
    }
```

```python
# update backend/app/infrastructure/persistence/factory.py
from app.application.services.source_routing_service import SourceRoutingService


def build_source_routing_service() -> SourceRoutingService:
    return SourceRoutingService(health_repo=build_source_health_repository())


def build_source_read_service() -> SourceReadService:
    return SourceReadService(
        build_source_repository(),
        LegadoBookSourceFetcher(),
        routing_service=build_source_routing_service(),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_routing_service.py tests\test_source_read_service.py -v`
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\application\services\source_routing_service.py docs\superpowers\reports\checkpoints\2026-07-09-source-health-task4-search-routing.py`
Expected: checkpoint file exists.

### Task 5: Add TOC/content health gating and fallback resolution

**Files:**
- Modify: `backend/app/application/services/source_routing_service.py`
- Modify: `backend/app/application/services/source_read_service.py`
- Modify: `backend/app/interfaces/http/reading.py`
- Modify: `backend/tests/test_source_read_service.py`

- [ ] **Step 1: Write the failing fallback tests**

```python
import pytest


@pytest.mark.asyncio
async def test_get_book_toc_falls_back_to_alternate_source_when_primary_is_blocked():
    from app.application.services.source_read_service import SourceReadService

    class Repo:
        async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
            all_sources = [
                {"id": 1, "bookSourceName": "Primary", "bookSourceUrl": "https://a.example.com", "enabled": True},
                {"id": 2, "bookSourceName": "Fallback", "bookSourceUrl": "https://b.example.com", "enabled": True},
            ]
            return [item for item in all_sources if ids is None or item["id"] in ids]

    class Fetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "author": "唐家三少", "bookUrl": source["bookSourceUrl"] + "/book/1"}]

        async def get_toc(self, source, book_url):
            if source["id"] == 1:
                return []
            return [{"title": "第一章 入世", "url": book_url + "/1"}]

        async def get_content(self, source, chapter_url):
            return {"content": "正文", "title": "第一章 入世", "nextUrl": ""}

    class RoutingService:
        def snapshot_map(self, source_ids):
            return {1: type("Snap", (), {"health_status": "blocked", "failure_reason": "waf_blocked", "route_policy": "skip", "route_score": 0})(), 2: type("Snap", (), {"health_status": "healthy", "failure_reason": "", "route_policy": "allow", "route_score": 100})()}

        def rank_search_sources(self, sources, snapshots, routing_mode="auto"):
            return [{"source": sources[1], "decision": {"health_status": "healthy", "failure_reason": "", "route_decision": "allow", "route_score": 100}}]

    service = SourceReadService(repo=Repo(), fetcher=Fetcher(), routing_service=RoutingService())
    result = await service.get_book_toc(
        source_id=1,
        book_url="https://a.example.com/book/1",
        book_name="斗罗大陆",
        author_hint="唐家三少",
        routing_mode="auto",
    )

    assert result["resolved_source_id"] == 2
    assert result["fallback_used"] is True
    assert result["chapters"][0]["title"] == "第一章 入世"


@pytest.mark.asyncio
async def test_get_chapter_content_falls_back_by_chapter_index():
    from app.application.services.source_read_service import SourceReadService

    class Repo:
        async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
            all_sources = [
                {"id": 1, "bookSourceName": "Primary", "bookSourceUrl": "https://a.example.com", "enabled": True},
                {"id": 2, "bookSourceName": "Fallback", "bookSourceUrl": "https://b.example.com", "enabled": True},
            ]
            return [item for item in all_sources if ids is None or item["id"] in ids]

    class Fetcher:
        async def search(self, source, keyword, page=1):
            return [{"name": keyword, "author": "南派三叔", "bookUrl": source["bookSourceUrl"] + "/book/1"}]

        async def get_toc(self, source, book_url):
            return [
                {"title": "第一章 出发", "url": book_url + "/1", "index": 0},
                {"title": "第二章 夜路", "url": book_url + "/2", "index": 1},
            ]

        async def get_content(self, source, chapter_url):
            if source["id"] == 1:
                return {"content": "", "title": "第二章 夜路", "nextUrl": ""}
            return {"content": "补源正文", "title": "第二章 夜路", "nextUrl": ""}

    class RoutingService:
        def snapshot_map(self, source_ids):
            return {1: type("Snap", (), {"health_status": "degraded", "failure_reason": "parse_empty", "route_policy": "deprioritize", "route_score": 30})(), 2: type("Snap", (), {"health_status": "healthy", "failure_reason": "", "route_policy": "allow", "route_score": 100})()}

        def rank_search_sources(self, sources, snapshots, routing_mode="auto"):
            return [{"source": sources[1], "decision": {"health_status": "healthy", "failure_reason": "", "route_decision": "allow", "route_score": 100}}]

    service = SourceReadService(repo=Repo(), fetcher=Fetcher(), routing_service=RoutingService())
    result = await service.get_chapter_content(
        source_id=1,
        chapter_url="https://a.example.com/book/1/2",
        book_name="捞尸人",
        author_hint="南派三叔",
        chapter_title="第二章 夜路",
        chapter_index=1,
        routing_mode="auto",
    )

    assert result["resolved_source_id"] == 2
    assert result["fallback_used"] is True
    assert result["content"] == "补源正文"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_read_service.py -v`
Expected: FAIL because `get_book_toc()` and `get_chapter_content()` do not support routing-mode fallback.

- [ ] **Step 3: Write the minimal TOC/content fallback implementation**

```python
# extend backend/app/application/services/source_routing_service.py
    async def resolve_book_candidates(self, repo, keyword: str, author_hint: str | None, fetcher, routing_mode: str = "auto") -> list[dict]:
        sources = await repo.list_book_sources_full(enabled_only=True)
        ranked = self.rank_search_sources(sources, self.snapshot_map([source["id"] for source in sources]), routing_mode=routing_mode)
        candidates = []
        for routed in ranked:
            source = routed["source"]
            results = await fetcher.search(source, keyword, page=1)
            if results:
                candidates.append({"source": source, "book": results[0], "decision": routed["decision"]})
        return candidates
```

```python
# extend backend/app/application/services/source_read_service.py
    async def get_book_toc(
        self,
        source_id: int,
        book_url: str,
        book_name: str | None = None,
        author_hint: str | None = None,
        routing_mode: str = "auto",
    ) -> dict:
        source = await self._get_source_or_raise(source_id)
        chapters = await self._fetcher.get_toc(source, book_url)
        if chapters or not book_name or self._routing_service is None:
            return {
                "source_id": source_id,
                "resolved_source_id": source_id,
                "book_url": book_url,
                "chapters": chapters,
                "fallback_used": False,
            }

        candidates = await self._routing_service.resolve_book_candidates(self._repo, book_name, author_hint, self._fetcher, routing_mode=routing_mode)
        for candidate in candidates:
            if candidate["source"]["id"] == source_id:
                continue
            alt_chapters = await self._fetcher.get_toc(candidate["source"], candidate["book"]["bookUrl"])
            if alt_chapters:
                return {
                    "source_id": source_id,
                    "resolved_source_id": candidate["source"]["id"],
                    "book_url": candidate["book"]["bookUrl"],
                    "chapters": alt_chapters,
                    "fallback_used": True,
                }

        return {"source_id": source_id, "resolved_source_id": source_id, "book_url": book_url, "chapters": chapters, "fallback_used": False}

    async def get_chapter_content(
        self,
        source_id: int,
        chapter_url: str,
        book_name: str | None = None,
        author_hint: str | None = None,
        chapter_title: str | None = None,
        chapter_index: int | None = None,
        routing_mode: str = "auto",
    ) -> dict:
        source = await self._get_source_or_raise(source_id)
        content = await self._fetcher.get_content(source, chapter_url)
        if content.get("content") or not book_name or self._routing_service is None:
            return {"source_id": source_id, "resolved_source_id": source_id, "chapter_url": chapter_url, "fallback_used": False, **content}

        candidates = await self._routing_service.resolve_book_candidates(self._repo, book_name, author_hint, self._fetcher, routing_mode=routing_mode)
        for candidate in candidates:
            if candidate["source"]["id"] == source_id:
                continue
            chapters = await self._fetcher.get_toc(candidate["source"], candidate["book"]["bookUrl"])
            match = None
            if chapter_index is not None:
                match = next((item for item in chapters if int(item.get("index", -1)) == chapter_index), None)
            if match is None and chapter_title:
                match = next((item for item in chapters if item.get("title") == chapter_title), None)
            if match is None:
                continue
            alt_content = await self._fetcher.get_content(candidate["source"], match["url"])
            if alt_content.get("content"):
                return {
                    "source_id": source_id,
                    "resolved_source_id": candidate["source"]["id"],
                    "chapter_url": match["url"],
                    "fallback_used": True,
                    **alt_content,
                }

        return {"source_id": source_id, "resolved_source_id": source_id, "chapter_url": chapter_url, "fallback_used": False, **content}
```

```python
# extend backend/app/interfaces/http/reading.py
class ReadingTocRequest(BaseModel):
    source_id: int
    book_url: str
    book_name: str | None = None
    author_hint: str | None = None
    routing_mode: str = "auto"


class ReadingContentRequest(BaseModel):
    source_id: int
    chapter_url: str
    book_name: str | None = None
    author_hint: str | None = None
    chapter_title: str | None = None
    chapter_index: int | None = None
    routing_mode: str = "auto"


@router.post("/toc")
async def get_book_toc(payload: ReadingTocRequest, _=Depends(require_permission(Permission.BOOK_SOURCES_READ))):
    service = build_source_read_service()
    data = await service.get_book_toc(
        payload.source_id,
        payload.book_url,
        payload.book_name,
        payload.author_hint,
        payload.routing_mode,
    )
    return {"success": True, "code": "OK", "message": "toc loaded", "data": data, "meta": {"total": len(data["chapters"]), "resolved_source_id": data["resolved_source_id"], "fallback_used": data["fallback_used"]}, "trace_id": None}


@router.post("/content")
async def get_chapter_content(payload: ReadingContentRequest, _=Depends(require_permission(Permission.BOOK_SOURCES_READ))):
    service = build_source_read_service()
    data = await service.get_chapter_content(
        payload.source_id,
        payload.chapter_url,
        payload.book_name,
        payload.author_hint,
        payload.chapter_title,
        payload.chapter_index,
        payload.routing_mode,
    )
    return {"success": True, "code": "OK", "message": "content loaded", "data": data, "meta": {"resolved_source_id": data["resolved_source_id"], "fallback_used": data["fallback_used"]}, "trace_id": None}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_read_service.py -v`
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\application\services\source_read_service.py docs\superpowers\reports\checkpoints\2026-07-09-source-health-task5-read-fallback.py`
Expected: checkpoint file exists.

### Task 6: Expose source-health HTTP APIs and wire them into the application

**Files:**
- Create: `backend/app/interfaces/http/source_health.py`
- Modify: `backend/app/interfaces/http/router.py`
- Modify: `backend/app/infrastructure/persistence/factory.py`
- Create: `backend/tests/test_api_source_health.py`

- [ ] **Step 1: Write the failing API test**

```python
from fastapi.testclient import TestClient


def test_source_health_endpoints_require_auth_and_return_probe_payload(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "source-health-api.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    token = create_access_token({"sub": "1", "permissions": ["book_sources.read", "book_sources.write"], "sid": "source-health-1"})

    unauth = client.get("/api/source-health/book-sources")
    assert unauth.status_code == 401

    auth = client.get("/api/source-health/book-sources", headers={"Authorization": f"Bearer {token}"})
    assert auth.status_code == 200
    assert auth.json()["success"] is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_api_source_health.py -v`
Expected: FAIL because the `/api/source-health/*` router does not exist.

- [ ] **Step 3: Write the minimal HTTP API implementation**

```python
# backend/app/interfaces/http/source_health.py
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_source_health_admin_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


class ProbeRequest(BaseModel):
    keyword_samples: list[str] = ["捞尸人", "斗罗大陆"]
    probe_mode: str = "full_chain"


class ProbeBatchRequest(BaseModel):
    source_ids: list[int]
    keyword_samples: list[str] = ["捞尸人", "斗罗大陆"]
    probe_mode: str = "full_chain"


class QuarantineRequest(BaseModel):
    note: str = "manual_quarantine"


@router.get("/book-sources")
async def list_book_source_health(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    statuses: str | None = None,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_health_admin_service()
    data = await service.list_book_source_health(
        page=page,
        page_size=page_size,
        statuses=statuses.split(",") if statuses else None,
    )
    return {"success": True, "code": "OK", "message": "source health listed", "data": data["items"], "meta": data["meta"], "trace_id": None}


@router.get("/book-sources/{source_id}")
async def get_book_source_health(source_id: int, _=Depends(require_permission(Permission.BOOK_SOURCES_READ))):
    service = build_source_health_admin_service()
    data = await service.get_book_source_health(source_id)
    return {"success": True, "code": "OK", "message": "source health loaded", "data": data, "meta": {}, "trace_id": None}


@router.post("/book-sources/{source_id}/probe")
async def probe_book_source(source_id: int, payload: ProbeRequest, _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE))):
    service = build_source_health_admin_service()
    data = await service.probe_book_source(source_id, keyword_samples=payload.keyword_samples, probe_mode=payload.probe_mode)
    return {"success": True, "code": "OK", "message": "source probed", "data": data, "meta": {}, "trace_id": None}


@router.post("/book-sources/probe-batch")
async def probe_book_sources(payload: ProbeBatchRequest, _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE))):
    service = build_source_health_admin_service()
    data = await service.probe_book_sources(payload.source_ids, keyword_samples=payload.keyword_samples, probe_mode=payload.probe_mode)
    return {"success": True, "code": "OK", "message": "source probe batch completed", "data": data["results"], "meta": {"total": data["total"]}, "trace_id": None}


@router.post("/book-sources/{source_id}/recover")
async def recover_book_source(source_id: int, _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE))):
    service = build_source_health_admin_service()
    data = await service.recover_source(source_id)
    return {"success": True, "code": "OK", "message": "source recovered", "data": data, "meta": {}, "trace_id": None}


@router.post("/book-sources/{source_id}/quarantine")
async def quarantine_book_source(source_id: int, payload: QuarantineRequest, _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE))):
    service = build_source_health_admin_service()
    data = await service.quarantine_source(source_id, note=payload.note)
    return {"success": True, "code": "OK", "message": "source quarantined", "data": data, "meta": {}, "trace_id": None}
```

```python
# update backend/app/interfaces/http/router.py
from app.interfaces.http import admin, ai, auth, dashboard, engine, export, health, novel, reading, source_health, sources, system, translation

api_router.include_router(source_health.router, prefix="/source-health", tags=["source-health"])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_api_source_health.py -v`
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\app\interfaces\http\source_health.py docs\superpowers\reports\checkpoints\2026-07-09-source-health-task6-http.py`
Expected: checkpoint file exists.

### Task 7: Add scheduler entrypoints and real-source health regression scripts

**Files:**
- Modify: `backend/app/tasks/scheduler.py`
- Create: `backend/scripts/probe_source_health.py`
- Modify: `backend/scripts/search_real_books.py`
- Modify: `backend/scripts/smoke_js_compat_sources.py`
- Modify: `backend/tests/test_source_health_scheduler.py`

- [ ] **Step 1: Write the failing scheduler/script test**

```python
import pytest


@pytest.mark.asyncio
async def test_run_source_health_probe_job_invokes_admin_service(monkeypatch):
    from app.tasks import scheduler

    class FakeAdminService:
        async def probe_book_sources(self, source_ids, keyword_samples, probe_mode="full_chain"):
            return {
                "results": [{"snapshot": {"health_status": "healthy", "source_id": 7}}],
                "total": 1,
            }

    monkeypatch.setattr(scheduler, "build_source_health_admin_service", lambda: FakeAdminService())

    result = await scheduler.run_source_health_probe_job(source_ids=[7], keyword_samples=["斗罗大陆"])

    assert result["total"] == 1
    assert result["results"][0]["snapshot"]["health_status"] == "healthy"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_health_scheduler.py -v`
Expected: FAIL because `run_source_health_probe_job()` does not exist.

- [ ] **Step 3: Write the minimal scheduler and script implementation**

```python
# add to backend/app/tasks/scheduler.py
from ..infrastructure.persistence.factory import build_source_health_admin_service


async def run_source_health_probe_job(
    source_ids: list[int],
    keyword_samples: list[str],
    probe_mode: str = "full_chain",
) -> dict:
    service = build_source_health_admin_service()
    return await service.probe_book_sources(source_ids, keyword_samples=keyword_samples, probe_mode=probe_mode)
```

```python
# backend/scripts/probe_source_health.py
from pathlib import Path
import argparse
import asyncio
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-32-bytes-minimum")

from app.infrastructure.persistence.factory import build_source_health_admin_service


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-ids", nargs="+", type=int, required=True)
    parser.add_argument("--keywords", nargs="+", default=["捞尸人", "斗罗大陆"])
    parser.add_argument("--probe-mode", default="full_chain")
    args = parser.parse_args()

    service = build_source_health_admin_service()
    result = await service.probe_book_sources(args.source_ids, keyword_samples=args.keywords, probe_mode=args.probe_mode)
    print(f"[source-health] total={result['total']}")
    for item in result["results"]:
        snapshot = item["snapshot"]
        print(
            f"  - source_id={snapshot['source_id']} "
            f"status={snapshot['health_status']} "
            f"search={snapshot['search_status']} toc={snapshot['toc_status']} content={snapshot['content_status']} "
            f"reason={snapshot['failure_reason']} policy={snapshot['route_policy']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
```

```python
# update backend/scripts/search_real_books.py
        for keyword in DEFAULT_KEYWORDS:
            result = await service.search_books(
                keyword=keyword,
                source_ids=DEFAULT_SOURCE_IDS,
                limit_per_source=3,
                author_hint=DEFAULT_AUTHOR_HINTS.get(keyword),
                routing_mode="auto",
                include_health=True,
            )
            print(f"[search] keyword={keyword} hits={len(result['items'])} route={result['route_summary']}")
            for item in result["items"][:10]:
                print(
                    f"  - [source_id={item['source_id']}] "
                    f"[{item['sourceName']}] {item['name']} / {item['author']} "
                    f"health={item.get('health_status')} "
                    f"decision={item.get('route_decision')} "
                    f"reason={item.get('failure_reason') or '-'}"
                )
```

```python
# update backend/scripts/smoke_js_compat_sources.py
from app.infrastructure.persistence.factory import build_source_health_admin_service, build_source_read_service

        admin_service = build_source_health_admin_service()
        for source in js_sources:
            probe = await admin_service.probe_book_source(source["id"], keyword_samples=[DEFAULT_KEYWORDS[0]], probe_mode="search_only")
            snapshot = probe["snapshot"]
            print(
                f"[js-compat] source_id={source['id']} name={source.get('bookSourceName', '')} "
                f"health={snapshot['health_status']} reason={snapshot['failure_reason']} "
                f"search={snapshot['search_status']} toc={snapshot['toc_status']} content={snapshot['content_status']}"
            )
```

- [ ] **Step 4: Run the tests and real-source scripts**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_source_health_scheduler.py -v`
Expected: PASS.

Run: `\.venv\Scripts\python.exe scripts\probe_source_health.py --source-ids 7 33 --keywords 捞尸人 斗罗大陆`
Expected: prints per-source `status/search/toc/content/reason/policy` lines.

Run: `\.venv\Scripts\python.exe scripts\search_real_books.py`
Expected: existing real source hits remain, plus `route=` and item-level health/decision fields.

Run: `\.venv\Scripts\python.exe scripts\smoke_js_compat_sources.py`
Expected: JS-heavy sources print `health=` and `reason=` classifications instead of only `exec=ok/fail`.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item backend\scripts\probe_source_health.py docs\superpowers\reports\checkpoints\2026-07-09-source-health-task7-scripts.py`
Expected: checkpoint file exists.

### Task 8: Add the frontend source-health control plane

**Files:**
- Create: `frontend/src/api/modules/sourceHealth.ts`
- Create: `frontend/src/features/sources/SourceHealthPage.tsx`
- Create: `frontend/src/features/sources/SourceHealthPage.test.tsx`
- Modify: `frontend/src/features/sources/SourceListPage.tsx`
- Modify: `frontend/src/app/router.tsx`

- [ ] **Step 1: Write the failing frontend test**

```tsx
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

vi.mock('@/api/modules/sourceHealth', () => ({
  listSourceHealth: vi.fn().mockResolvedValue({
    success: true,
    code: 'OK',
    message: 'ok',
    data: [
      {
        source_id: 7,
        source_name: '七猫小说',
        source_url: 'https://www.qimao.com',
        health_status: 'healthy',
        search_status: 'ok',
        toc_status: 'ok',
        content_status: 'ok',
        failure_reason: '',
        route_policy: 'allow',
      },
      {
        source_id: 4,
        source_name: '起点读书限免+本章说',
        source_url: 'https://www.qidian.com',
        health_status: 'blocked',
        search_status: 'failed',
        toc_status: 'skipped',
        content_status: 'skipped',
        failure_reason: 'token_missing',
        route_policy: 'skip',
      },
    ],
    meta: { page: 1, page_size: 20, total: 2 },
    trace_id: null,
  }),
  probeSourceHealth: vi.fn().mockResolvedValue({ success: true, code: 'OK', message: 'ok', data: {}, meta: {}, trace_id: null }),
  recoverSourceHealth: vi.fn().mockResolvedValue({ success: true, code: 'OK', message: 'ok', data: {}, meta: {}, trace_id: null }),
}))

import { SourceHealthPage } from './SourceHealthPage'

test('source health page shows stage statuses and failure reasons', async () => {
  render(
    <MemoryRouter>
      <SourceHealthPage />
    </MemoryRouter>
  )

  expect(await screen.findByText('Source health control plane')).toBeInTheDocument()
  expect(await screen.findByText('token_missing')).toBeInTheDocument()
  expect(await screen.findByText('Probe now')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm --prefix frontend run test -- src/features/sources/SourceHealthPage.test.tsx --run`
Expected: FAIL because the source health API module and page do not exist.

- [ ] **Step 3: Write the minimal frontend implementation**

```ts
// frontend/src/api/modules/sourceHealth.ts
import { apiClient } from '@/api/client'
import type { ApiEnvelope } from '@/api/types'

export interface SourceHealthRow {
  source_id: number
  source_name: string
  source_url: string
  health_status: string
  search_status: string
  toc_status: string
  content_status: string
  failure_reason: string
  route_policy: string
  route_score?: number
}

export async function listSourceHealth(params: { page?: number; page_size?: number; statuses?: string } = {}) {
  return apiClient.get<SourceHealthRow[]>('/source-health/book-sources', { params }) as Promise<ApiEnvelope<SourceHealthRow[]>>
}

export async function probeSourceHealth(sourceId: number, keywordSamples = ['捞尸人', '斗罗大陆']) {
  return apiClient.post(`/source-health/book-sources/${sourceId}/probe`, { keyword_samples: keywordSamples, probe_mode: 'full_chain' })
}

export async function recoverSourceHealth(sourceId: number) {
  return apiClient.post(`/source-health/book-sources/${sourceId}/recover`)
}
```

```tsx
// frontend/src/features/sources/SourceHealthPage.tsx
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { listSourceHealth, probeSourceHealth, recoverSourceHealth, type SourceHealthRow } from '@/api/modules/sourceHealth'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'

function tone(status: string) {
  if (status === 'healthy' || status === 'ok') return 'text-emerald-300'
  if (status === 'degraded') return 'text-amber-300'
  if (status === 'blocked' || status === 'failed' || status === 'dead') return 'text-rose-300'
  return 'text-zinc-400'
}

export function SourceHealthPage() {
  const [rows, setRows] = useState<SourceHealthRow[]>([])
  const [loading, setLoading] = useState(true)

  async function load() {
    const response = await listSourceHealth({ page: 1, page_size: 20 })
    setRows(response.data)
    setLoading(false)
  }

  useEffect(() => {
    void load()
  }, [])

  async function handleProbe(sourceId: number) {
    await probeSourceHealth(sourceId)
    await load()
  }

  async function handleRecover(sourceId: number) {
    await recoverSourceHealth(sourceId)
    await load()
  }

  const summary = rows.reduce(
    (acc, row) => {
      acc.total += 1
      acc[row.health_status] = (acc[row.health_status] || 0) + 1
      return acc
    },
    { total: 0 } as Record<string, number>
  )

  return (
    <ConsoleLayout
      eyebrow="Source Health"
      title="Source health control plane"
      description="展示 search / toc / content 三层状态、失败原因、分流策略，并提供重探测与恢复入口。"
    >
      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-[24px] border border-white/10 bg-black/20 p-5">Total: {summary.total || 0}</div>
        <div className="rounded-[24px] border border-white/10 bg-black/20 p-5">Healthy: {summary.healthy || 0}</div>
        <div className="rounded-[24px] border border-white/10 bg-black/20 p-5">Blocked: {summary.blocked || 0}</div>
        <div className="rounded-[24px] border border-white/10 bg-black/20 p-5">Dead: {summary.dead || 0}</div>
      </div>

      <section className="rounded-[24px] border border-white/10 bg-black/20 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-xl font-semibold text-white">Book source health</h3>
          <Link to="/sources" className="text-sm text-cyan-300">Back to inventory</Link>
        </div>

        {loading ? (
          <div className="text-sm text-zinc-400">Loading</div>
        ) : (
          <div className="space-y-4">
            {rows.map((row) => (
              <article key={row.source_id} className="rounded-2xl border border-white/8 bg-white/5 p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h4 className="text-lg font-semibold text-white">{row.source_name}</h4>
                    <p className="text-sm text-zinc-400">{row.source_url}</p>
                    <p className={`mt-2 text-sm ${tone(row.health_status)}`}>health: {row.health_status}</p>
                    <p className="mt-1 text-sm text-zinc-300">reason: {row.failure_reason || '-'}</p>
                  </div>
                  <div className="flex gap-2">
                    <button className="rounded-xl border border-cyan-400/30 px-3 py-2 text-sm text-cyan-200" onClick={() => void handleProbe(row.source_id)}>
                      Probe now
                    </button>
                    <button className="rounded-xl border border-emerald-400/30 px-3 py-2 text-sm text-emerald-200" onClick={() => void handleRecover(row.source_id)}>
                      Recover
                    </button>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 md:grid-cols-3">
                  <div className={`rounded-xl border border-white/10 p-3 text-sm ${tone(row.search_status)}`}>search: {row.search_status}</div>
                  <div className={`rounded-xl border border-white/10 p-3 text-sm ${tone(row.toc_status)}`}>toc: {row.toc_status}</div>
                  <div className={`rounded-xl border border-white/10 p-3 text-sm ${tone(row.content_status)}`}>content: {row.content_status}</div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </ConsoleLayout>
  )
}
```

```tsx
// update frontend/src/features/sources/SourceListPage.tsx
import { Link } from 'react-router-dom'

      <div className="flex justify-end">
        <Link to="/sources/health" className="rounded-2xl border border-cyan-400/30 px-4 py-2 text-sm text-cyan-200">
          Open source health control plane
        </Link>
      </div>
```

```tsx
// update frontend/src/app/router.tsx
import { SourceHealthPage } from '@/features/sources/SourceHealthPage'

export const appRoutes = [
  { path: '/login', element: <LoginPage /> },
  { path: '/sources', element: <SourceListPage /> },
  { path: '/sources/health', element: <SourceHealthPage /> },
  { path: '/engine', element: <EngineRunsPage /> },
  { path: '/admin/users', element: <AdminUsersPage /> },
  { path: '/admin/audit', element: <AdminAuditPage /> },
  { path: '/ai/tasks', element: <AITasksPage /> },
  { path: '/translation/jobs', element: <TranslationJobsPage /> },
  { path: '/novel/tasks', element: <NovelTasksPage /> },
  { path: '/system/settings', element: <SystemSettingsPage /> },
]

<Route path="/login" element={<LoginPage />} />
<Route path="/sources" element={<SourceListPage />} />
<Route path="/sources/health" element={<SourceHealthPage />} />
<Route path="/engine" element={<EngineRunsPage />} />
<Route path="/admin/users" element={<AdminUsersPage />} />
<Route path="/admin/audit" element={<AdminAuditPage />} />
<Route path="/ai/tasks" element={<AITasksPage />} />
<Route path="/translation/jobs" element={<TranslationJobsPage />} />
<Route path="/novel/tasks" element={<NovelTasksPage />} />
<Route path="/system/settings" element={<SystemSettingsPage />} />
<Route path="/" element={<Navigate to="/login" replace />} />
<Route path="*" element={<Navigate to="/login" replace />} />
```

- [ ] **Step 4: Run the frontend test to verify it passes**

Run: `npm --prefix frontend run test -- src/features/sources/SourceHealthPage.test.tsx --run`
Expected: PASS.

- [ ] **Step 5: Filesystem checkpoint**

Run: `Copy-Item frontend\src\features\sources\SourceHealthPage.tsx docs\superpowers\reports\checkpoints\2026-07-09-source-health-task8-frontend.tsx`
Expected: checkpoint file exists.

## Self-review

### Spec coverage

- Three-stage `search / toc / content` probing: Task 2.
- Failure reason classification and mixed recovery rules: Tasks 2 and 3.
- Snapshot persistence plus mirroring into `book_sources`: Tasks 1 and 3.
- Search-stage routing: Task 4.
- TOC/content fallback and gated reads: Task 5.
- Admin APIs and manual actions: Task 6.
- Scheduler / scripts / real-source regression: Task 7.
- Backend management panel: Task 8.

### Placeholder scan

- No placeholder markers remain.
- Each task includes exact file paths, concrete tests, commands, and a checkpoint step.
- No step says “write tests” or “add validation” without showing the exact code to start from.

### Type consistency

- Persistence types are `SourceHealthSnapshot` and `SourceProbeRun` throughout Tasks 1-8.
- Probe/classifier types are `StageProbeResult`, `SourceProbeEvidence`, and `SourceHealthDecision` throughout Tasks 2-7.
- Routing metadata uses the same field names in backend and frontend: `health_status`, `failure_reason`, `route_policy`, `route_score`, `search_status`, `toc_status`, `content_status`.
- The new service builders are consistently named `build_source_health_repository`, `build_source_probe_service`, `build_source_health_classifier_service`, `build_source_health_admin_service`, and `build_source_routing_service`.
