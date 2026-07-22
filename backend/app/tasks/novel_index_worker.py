"""Background consumer for persisted novel analysis/index tasks."""

from __future__ import annotations

import inspect
from uuid import uuid4
from typing import Any

from app.domain.entities.novel import NovelStatus
from app.domain.entities.novel_runtime import NovelAnalysisTask, NovelIngestion


class NovelIndexWorker:
    def __init__(self, *, index_service, runtime_repo, novel_repo=None):
        self._index_service = index_service
        self._runtime_repo = runtime_repo
        self._novel_repo = novel_repo

    async def run(self, *, limit: int = 10, owner_scope: str | None = None) -> dict[str, Any]:
        tasks = await self._resolve(self._runtime_repo.list_tasks(owner_scope))
        tasks = list(tasks or [])
        await self._discover_missing_tasks(tasks, owner_scope, max(0, int(limit)))
        tasks = await self._resolve(self._runtime_repo.list_tasks(owner_scope))
        tasks = list(tasks or [])
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
                    **(
                        task.result
                        if isinstance(task.result, dict) and task.result.get("auto_repair")
                        else {}
                    ),
                    "processed_chapters": indexed.processed_chapters,
                    "skipped_chapters": indexed.skipped_chapters,
                    "failed_chapters": indexed.failed_chapters,
                    "errors": indexed.errors,
                }
                self._runtime_repo.save_task(task)
                if self._novel_repo is not None:
                    await self._novel_repo.update_book_status(
                        task.owner_scope,
                        task.book_id,
                        NovelStatus.READY,
                        progress=1.0,
                    )
                outcomes.append({"task_id": task.id, "status": task.status, "result": task.result})
            except Exception as exc:
                task.status = "failed"
                task.result = {"error": str(exc)[:500]}
                self._runtime_repo.save_task(task)
                if self._novel_repo is not None:
                    await self._novel_repo.update_book_status(
                        task.owner_scope,
                        task.book_id,
                        NovelStatus.ERROR,
                        error_msg=str(exc)[:500],
                    )
                outcomes.append({"task_id": task.id, "status": task.status, "result": task.result})
        return {"processed": len(outcomes), "tasks": outcomes}

    async def _discover_missing_tasks(
        self,
        tasks: list[NovelAnalysisTask],
        owner_scope: str | None,
        limit: int,
    ) -> int:
        if self._novel_repo is None or limit <= 0:
            return 0
        list_books = getattr(self._novel_repo, "list_books", None)
        if not callable(list_books):
            return 0
        scope = owner_scope or "legacy"
        try:
            books = await self._resolve(list_books(scope, limit=10000, offset=0))
        except TypeError:
            books = await self._resolve(list_books(scope, limit=10000))
        active_by_book = {
            int(task.book_id)
            for task in tasks
            if task.book_id is not None and task.status in {"queued", "pending", "running"}
        }
        completed_repairs = {
            int(task.book_id)
            for task in tasks
            if task.book_id is not None
            and task.status in {"succeeded", "partial"}
            and isinstance(task.result, dict)
            and task.result.get("auto_repair")
        }
        created = 0
        for book in books or []:
            if created >= limit or book.id is None:
                break
            book_id = int(book.id)
            if book_id in active_by_book:
                continue
            reason = await self._repair_reason(scope, book)
            if reason is None:
                continue
            if book_id in completed_repairs and reason == "zero_statistics":
                # A completed repair may legitimately find no named entity in
                # a short chapter.  Do not enqueue it on every scheduler tick.
                continue
            task = await self._create_repair_task(scope, book, reason)
            if task is None:
                continue
            tasks.append(task)
            active_by_book.add(book_id)
            created += 1
        return created

    async def _repair_reason(self, owner_scope: str, book) -> str | None:
        count_chapters = getattr(self._novel_repo, "count_chapters", None)
        if not callable(count_chapters):
            return None
        chapter_count = await self._resolve(count_chapters(owner_scope, int(book.id)))
        if int(chapter_count or 0) <= 0:
            return None
        list_states = getattr(self._novel_repo, "list_index_states", None)
        states = []
        if callable(list_states):
            states = await self._resolve(list_states(owner_scope, int(book.id))) or []
        completed = [state for state in states if state.extraction_status == "completed"]
        if not completed:
            return "no_completed_state"
        if any(state.extraction_status in {"failed", "partial"} for state in states):
            return "failed_state"
        expected_version = str(getattr(self._index_service, "knowledge_version", "") or "")
        if expected_version and any(state.knowledge_version != expected_version for state in completed):
            return "knowledge_version"
        if len(completed) < int(chapter_count):
            return "missing_chapters"
        if int(getattr(book, "character_count", 0) or 0) == 0 or int(getattr(book, "entity_count", 0) or 0) == 0:
            return "zero_statistics"
        return None

    async def _create_repair_task(self, owner_scope: str, book, reason: str):
        novel_id = f"book:{int(book.id)}"
        save_ingestion = getattr(self._runtime_repo, "save_ingestion", None)
        if callable(save_ingestion):
            ingestion = NovelIngestion(
                id=uuid4().hex,
                owner_scope=owner_scope,
                book_id=int(book.id),
                title=str(getattr(book, "book_name", "") or ""),
                status="queued",
                pipeline="index-repair",
            )
            saved_ingestion = await self._resolve(save_ingestion(ingestion))
            novel_id = saved_ingestion.id
        task = NovelAnalysisTask(
            id=uuid4().hex,
            novel_id=novel_id,
            owner_scope=owner_scope,
            book_id=int(book.id),
            actor_id=owner_scope,
            status="queued",
            pipeline="index-repair",
            result={"auto_repair": True, "repair_reason": reason},
        )
        saved = self._runtime_repo.save_task(task)
        return await self._resolve(saved)

    @staticmethod
    async def _resolve(value):
        if inspect.isawaitable(value):
            return await value
        return value


async def run_novel_index_worker(*, index_service, runtime_repo, limit: int = 10, owner_scope: str | None = None):
    return await NovelIndexWorker(index_service=index_service, runtime_repo=runtime_repo).run(
        limit=limit,
        owner_scope=owner_scope,
    )
