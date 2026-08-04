import asyncio
from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_novel_index_job_injects_book_scoped_adaptive_learning(monkeypatch):
    from app.application.services.novel_understanding.adaptive_learning import AdaptiveLearningService
    from app.infrastructure.persistence import factory
    from app.tasks import novel_index_worker
    from app.tasks.scheduler import run_novel_index_job

    repo = object()
    runtime_repo = object()
    captured = {}

    async def build_repo():
        return repo

    class Worker:
        def __init__(self, *, index_service, runtime_repo, novel_repo):
            captured["index_service"] = index_service

        async def run(self, **kwargs):
            return {"processed": 0, "tasks": []}

    monkeypatch.setattr(factory, "build_novel_repository", build_repo)
    monkeypatch.setattr(factory, "build_novel_runtime_repository", lambda: runtime_repo)
    monkeypatch.setattr(factory, "build_provider_platform_service", lambda: object())
    monkeypatch.setattr(factory, "build_vector_store", lambda: object())
    monkeypatch.setattr(novel_index_worker, "NovelIndexWorker", Worker)

    await run_novel_index_job(limit=1, owner_scope="user:1")

    learning = captured["index_service"].adaptive_learning
    assert isinstance(learning, AdaptiveLearningService)
    assert learning._repo is repo


@pytest.mark.asyncio
async def test_novel_index_worker_consumes_queued_analysis_tasks():
    from app.domain.entities.novel_runtime import NovelAnalysisTask
    from app.tasks.novel_index_worker import NovelIndexWorker

    task = NovelAnalysisTask(
        id="task-1",
        novel_id="ingestion-1",
        owner_scope="user:1",
        book_id=7,
        status="queued",
    )

    class RuntimeRepo:
        def __init__(self):
            self.tasks = [task]

        def list_tasks(self, owner_scope=None):
            return [item for item in self.tasks if owner_scope is None or item.owner_scope == owner_scope]

        def save_task(self, value):
            self.tasks[0] = value
            return value

    class IndexService:
        async def index_book(self, owner_scope, book_id, from_chapter=None):
            return type(
                "IndexResult",
                (),
                {"processed_chapters": 2, "skipped_chapters": 0, "failed_chapters": 0, "errors": []},
            )()

    runtime = RuntimeRepo()
    worker = NovelIndexWorker(index_service=IndexService(), runtime_repo=runtime)
    output = await worker.run(limit=1, owner_scope="user:1")

    assert output["processed"] == 1
    assert runtime.tasks[0].status == "succeeded"
    assert runtime.tasks[0].result["processed_chapters"] == 2


@pytest.mark.asyncio
async def test_novel_index_worker_persists_structured_index_result_status():
    from app.domain.entities.novel_runtime import NovelAnalysisTask
    from app.tasks.novel_index_worker import NovelIndexWorker

    task = NovelAnalysisTask(
        id="task-result-details",
        novel_id="ingestion-result-details",
        owner_scope="user:1",
        book_id=7,
        status="queued",
    )

    class RuntimeRepo:
        def __init__(self):
            self.tasks = [task]

        def list_tasks(self, owner_scope=None):
            return self.tasks

        def save_task(self, value):
            self.tasks[0] = value
            return value

    class IndexService:
        async def index_book(self, owner_scope, book_id, from_chapter=None):
            return type(
                "IndexResult",
                (),
                {
                    "processed_chapters": 0,
                    "skipped_chapters": 0,
                    "failed_chapters": 0,
                    "errors": [],
                    "status": "no_chapters",
                    "no_chapters": True,
                    "indexed_chapters": [0],
                    "timings_ms": {"chapters": 2, "total": 3},
                },
            )()

    runtime = RuntimeRepo()
    await NovelIndexWorker(index_service=IndexService(), runtime_repo=runtime).run(limit=1)

    result = runtime.tasks[0].result
    assert result["status"] == "no_chapters"
    assert result["no_chapters"] is True
    assert result["indexed_chapters"] == [0]
    assert result["timings_ms"] == {"chapters": 2, "total": 3}


@pytest.mark.asyncio
async def test_novel_index_worker_marks_book_ready_after_successful_analysis():
    from app.domain.entities.novel import NovelStatus
    from app.domain.entities.novel_runtime import NovelAnalysisTask
    from app.tasks.novel_index_worker import NovelIndexWorker

    task = NovelAnalysisTask(
        id="task-ready",
        novel_id="ingestion-ready",
        owner_scope="user:1",
        book_id=7,
        status="queued",
    )

    class RuntimeRepo:
        def __init__(self):
            self.tasks = [task]

        def list_tasks(self, owner_scope=None):
            return [item for item in self.tasks if owner_scope is None or item.owner_scope == owner_scope]

        def save_task(self, value):
            self.tasks[0] = value
            return value

    class NovelRepo:
        def __init__(self):
            self.updates = []

        async def update_book_status(self, owner_scope, book_id, status, progress=None, error_msg=None):
            self.updates.append((owner_scope, book_id, status, progress, error_msg))
            return True

    class IndexService:
        async def index_book(self, owner_scope, book_id, from_chapter=None):
            return type(
                "IndexResult",
                (),
                {"processed_chapters": 2, "skipped_chapters": 1, "failed_chapters": 0, "errors": []},
            )()

    novel_repo = NovelRepo()
    worker = NovelIndexWorker(
        index_service=IndexService(),
        runtime_repo=RuntimeRepo(),
        novel_repo=novel_repo,
    )

    await worker.run(limit=1, owner_scope="user:1")

    assert novel_repo.updates == [("user:1", 7, NovelStatus.READY, 1.0, None)]


@pytest.mark.asyncio
async def test_novel_index_worker_requeues_stale_running_task_after_restart():
    from app.domain.entities.novel_runtime import NovelAnalysisTask
    from app.tasks.novel_index_worker import NovelIndexWorker

    task = NovelAnalysisTask(
        id="task-stale",
        novel_id="ingestion-stale",
        owner_scope="user:1",
        book_id=7,
        status="running",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    class RuntimeRepo:
        def __init__(self):
            self.tasks = [task]

        def list_tasks(self, owner_scope=None):
            return [item for item in self.tasks if owner_scope is None or item.owner_scope == owner_scope]

        def save_task(self, value):
            self.tasks[0] = value
            return value

    class IndexService:
        async def index_book(self, owner_scope, book_id, from_chapter=None):
            return type("IndexResult", (), {
                "processed_chapters": 1,
                "skipped_chapters": 0,
                "failed_chapters": 0,
                "errors": [],
            })()

    runtime = RuntimeRepo()
    result = await NovelIndexWorker(index_service=IndexService(), runtime_repo=runtime).run(
        limit=1, owner_scope="user:1"
    )

    assert result["processed"] == 1
    assert runtime.tasks[0].status == "succeeded"


@pytest.mark.asyncio
async def test_novel_index_worker_keeps_partial_book_out_of_ready_state():
    from app.domain.entities.novel import NovelStatus
    from app.domain.entities.novel_runtime import NovelAnalysisTask
    from app.tasks.novel_index_worker import NovelIndexWorker

    task = NovelAnalysisTask(
        id="task-partial",
        novel_id="ingestion-partial",
        owner_scope="user:1",
        book_id=7,
        status="queued",
    )

    class RuntimeRepo:
        def __init__(self):
            self.tasks = [task]

        def list_tasks(self, owner_scope=None):
            return [item for item in self.tasks if owner_scope is None or item.owner_scope == owner_scope]

        def save_task(self, value):
            self.tasks[0] = value
            return value

    class NovelRepo:
        def __init__(self):
            self.updates = []

        async def update_book_status(self, owner_scope, book_id, status, progress=None, error_msg=None):
            self.updates.append((owner_scope, book_id, status, progress, error_msg))
            return True

    class IndexService:
        async def index_book(self, owner_scope, book_id, from_chapter=None):
            return type("IndexResult", (), {
                "processed_chapters": 1,
                "skipped_chapters": 0,
                "failed_chapters": 1,
                "errors": [{"chapter_id": 2, "error": "bad chapter"}],
            })()

    novel_repo = NovelRepo()
    await NovelIndexWorker(
        index_service=IndexService(), runtime_repo=RuntimeRepo(), novel_repo=novel_repo
    ).run(limit=1, owner_scope="user:1")

    assert novel_repo.updates[0][2] == NovelStatus.EXTRACTING
    assert novel_repo.updates[0][3] < 1.0


@pytest.mark.asyncio
async def test_novel_index_worker_marks_book_error_when_analysis_fails():
    from app.domain.entities.novel import NovelStatus
    from app.domain.entities.novel_runtime import NovelAnalysisTask
    from app.tasks.novel_index_worker import NovelIndexWorker

    task = NovelAnalysisTask(
        id="task-error",
        novel_id="ingestion-error",
        owner_scope="user:1",
        book_id=7,
        status="queued",
    )

    class RuntimeRepo:
        def __init__(self):
            self.tasks = [task]

        def list_tasks(self, owner_scope=None):
            return [item for item in self.tasks if owner_scope is None or item.owner_scope == owner_scope]

        def save_task(self, value):
            self.tasks[0] = value
            return value

    class NovelRepo:
        def __init__(self):
            self.updates = []

        async def update_book_status(self, owner_scope, book_id, status, progress=None, error_msg=None):
            self.updates.append((owner_scope, book_id, status, progress, error_msg))
            return True

    class IndexService:
        async def index_book(self, owner_scope, book_id, from_chapter=None):
            raise RuntimeError("provider unavailable")

    novel_repo = NovelRepo()
    worker = NovelIndexWorker(
        index_service=IndexService(),
        runtime_repo=RuntimeRepo(),
        novel_repo=novel_repo,
    )

    await worker.run(limit=1, owner_scope="user:1")

    assert novel_repo.updates == [("user:1", 7, NovelStatus.ERROR, None, "provider unavailable")]


@pytest.mark.asyncio
async def test_novel_index_worker_discovers_incomplete_book_and_deduplicates_repair_task():
    from app.domain.entities.novel import NovelBook
    from app.domain.entities.novel_runtime import NovelAnalysisTask, NovelIndexState
    from app.tasks.novel_index_worker import NovelIndexWorker

    book = NovelBook(id=7, book_url="https://repair.test", book_name="待修复书", owner_scope="user:1")

    class RuntimeRepo:
        def __init__(self):
            self.tasks = []

        def list_tasks(self, owner_scope=None):
            return [item for item in self.tasks if owner_scope is None or item.owner_scope == owner_scope]

        def save_task(self, value):
            for index, current in enumerate(self.tasks):
                if current.id == value.id:
                    self.tasks[index] = value
                    return value
            self.tasks.append(value)
            return value

    class NovelRepo:
        def __init__(self):
            self.states = []

        async def list_books(self, owner_scope, limit=10000):
            return [book]

        async def count_chapters(self, owner_scope, book_id):
            return 1

        async def list_index_states(self, owner_scope, book_id):
            return self.states

        async def update_book_status(self, *args, **kwargs):
            return True

    runtime = RuntimeRepo()
    novel_repo = NovelRepo()

    class IndexService:
        knowledge_version = "v2-local-evidence"

        async def index_book(self, owner_scope, book_id, from_chapter=None):
            novel_repo.states = [
                NovelIndexState(
                    owner_scope=owner_scope,
                    book_id=book_id,
                    chapter_id=1,
                    knowledge_version=self.knowledge_version,
                    extraction_status="completed",
                )
            ]
            return type(
                "IndexResult",
                (),
                {"processed_chapters": 1, "skipped_chapters": 0, "failed_chapters": 0, "errors": []},
            )()

    worker = NovelIndexWorker(index_service=IndexService(), runtime_repo=runtime, novel_repo=novel_repo)

    first = await worker.run(limit=1, owner_scope="user:1")
    second = await worker.run(limit=1, owner_scope="user:1")

    assert first["processed"] == 1
    assert second["processed"] == 0
    assert len(runtime.tasks) == 1
    assert runtime.tasks[0].status == "succeeded"


@pytest.mark.asyncio
async def test_novel_index_worker_global_discovery_preserves_book_owner_scope():
    from app.domain.entities.novel import NovelBook
    from app.tasks.novel_index_worker import NovelIndexWorker

    book = NovelBook(id=17, book_url="https://global-repair.test", book_name="用户书", owner_scope="user:9")

    class RuntimeRepo:
        def __init__(self):
            self.tasks = []

        def list_tasks(self, owner_scope=None):
            return [task for task in self.tasks if owner_scope is None or task.owner_scope == owner_scope]

        def save_task(self, task):
            self.tasks.append(task)
            return task

    class NovelRepo:
        async def list_books(self, owner_scope=None, limit=10000, offset=0):
            assert owner_scope is None
            return [book]

        async def count_chapters(self, owner_scope, book_id):
            assert owner_scope == "user:9"
            return 1

        async def list_index_states(self, owner_scope, book_id):
            return []

        async def update_book_status(self, *args, **kwargs):
            return True

    class IndexService:
        knowledge_version = "v2-local-evidence"

        async def index_book(self, owner_scope, book_id, from_chapter=None):
            assert owner_scope == "user:9"
            return type("IndexResult", (), {"processed_chapters": 1, "skipped_chapters": 0, "failed_chapters": 0, "errors": []})()

    runtime = RuntimeRepo()
    worker = NovelIndexWorker(index_service=IndexService(), runtime_repo=runtime, novel_repo=NovelRepo())

    result = await worker.run(limit=1)

    assert result["processed"] == 1
    assert runtime.tasks[0].owner_scope == "user:9"


@pytest.mark.asyncio
async def test_novel_index_worker_discovery_does_not_consume_capacity_already_queued():
    from app.domain.entities.novel import NovelBook
    from app.domain.entities.novel_runtime import NovelAnalysisTask
    from app.tasks.novel_index_worker import NovelIndexWorker

    queued = NovelAnalysisTask(id="existing", owner_scope="user:1", book_id=1, status="queued")
    missing = NovelBook(id=2, book_url="https://capacity-repair.test", book_name="待修复书", owner_scope="user:1")

    class RuntimeRepo:
        def __init__(self):
            self.tasks = [queued]

        def list_tasks(self, owner_scope=None):
            return [task for task in self.tasks if owner_scope is None or task.owner_scope == owner_scope]

        def save_task(self, task):
            for index, current in enumerate(self.tasks):
                if current.id == task.id:
                    self.tasks[index] = task
                    return task
            self.tasks.append(task)
            return task

    class NovelRepo:
        async def list_books(self, owner_scope, limit=10000, offset=0):
            return [missing]

        async def count_chapters(self, owner_scope, book_id):
            return 1

        async def list_index_states(self, owner_scope, book_id):
            return []

        async def update_book_status(self, *args, **kwargs):
            return True

    class IndexService:
        knowledge_version = "v2-local-evidence"

        async def index_book(self, owner_scope, book_id, from_chapter=None):
            return type("IndexResult", (), {"processed_chapters": 1, "skipped_chapters": 0, "failed_chapters": 0, "errors": []})()

    runtime = RuntimeRepo()
    worker = NovelIndexWorker(index_service=IndexService(), runtime_repo=runtime, novel_repo=NovelRepo())

    result = await worker.run(limit=1, owner_scope="user:1")

    assert result["processed"] == 1
    assert [task.id for task in runtime.tasks] == ["existing"]


@pytest.mark.asyncio
async def test_novel_index_loop_logs_failures_instead_of_silently_dropping_them(monkeypatch):
    from app import main

    stop_event = asyncio.Event()
    logged = []

    async def failing_job(limit):
        stop_event.set()
        raise RuntimeError("index failed")

    monkeypatch.setattr(main, "run_novel_index_job", failing_job)
    monkeypatch.setattr(main.logger, "exception", lambda *args, **kwargs: logged.append((args, kwargs)))

    await main._novel_index_worker(stop_event)

    assert logged
    assert "novel index worker iteration failed" in logged[0][0][0]
