"""Background consumer for persisted novel analysis/index tasks."""

from __future__ import annotations

from typing import Any


class NovelIndexWorker:
    def __init__(self, *, index_service, runtime_repo):
        self._index_service = index_service
        self._runtime_repo = runtime_repo

    async def run(self, *, limit: int = 10, owner_scope: str | None = None) -> dict[str, Any]:
        tasks = self._runtime_repo.list_tasks(owner_scope)
        queued = [
            task
            for task in tasks
            if task.status in {"queued", "pending"} and task.book_id is not None
        ][: max(0, int(limit))]
        outcomes = []
        for task in queued:
            task.status = "running"
            self._runtime_repo.save_task(task)
            try:
                indexed = await self._index_service.index_book(
                    task.owner_scope,
                    task.book_id,
                    from_chapter=task.chapter_id,
                )
                task.status = "succeeded" if indexed.failed_chapters == 0 else "partial"
                task.result = {
                    "processed_chapters": indexed.processed_chapters,
                    "skipped_chapters": indexed.skipped_chapters,
                    "failed_chapters": indexed.failed_chapters,
                    "errors": indexed.errors,
                }
                self._runtime_repo.save_task(task)
                outcomes.append({"task_id": task.id, "status": task.status, "result": task.result})
            except Exception as exc:
                task.status = "failed"
                task.result = {"error": str(exc)[:500]}
                self._runtime_repo.save_task(task)
                outcomes.append({"task_id": task.id, "status": task.status, "result": task.result})
        return {"processed": len(outcomes), "tasks": outcomes}


async def run_novel_index_worker(*, index_service, runtime_repo, limit: int = 10, owner_scope: str | None = None):
    return await NovelIndexWorker(index_service=index_service, runtime_repo=runtime_repo).run(
        limit=limit,
        owner_scope=owner_scope,
    )
