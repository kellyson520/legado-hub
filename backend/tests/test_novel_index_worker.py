import asyncio

import pytest


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
