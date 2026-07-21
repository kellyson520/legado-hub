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
