"""Background consumer for persisted novel analysis/index tasks."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any

from app.domain.entities.novel import NovelStatus
from app.domain.entities.novel_runtime import NovelAnalysisTask, NovelIngestion


class NovelIndexWorker:
    def __init__(self, *, index_service, runtime_repo, novel_repo=None, stale_running_after_seconds: int = 900):
        self._index_service = index_service
        self._runtime_repo = runtime_repo
        self._novel_repo = novel_repo
        self._stale_running_after = timedelta(seconds=max(1, int(stale_running_after_seconds)))

    async def run(self, *, limit: int = 10, owner_scope: str | None = None) -> dict[str, Any]:
        tasks = await self._resolve(self._runtime_repo.list_tasks(owner_scope))
        tasks = list(tasks or [])
        await self._requeue_stale_running_tasks(tasks)
        queued_count = sum(
            1
            for task in tasks
            if task.book_id is not None and task.status in {"queued", "pending"}
        )
        await self._discover_missing_tasks(tasks, owner_scope, max(0, int(limit) - queued_count))
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
            await self._save_task(task)
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
                    "indexed_chapters": list(getattr(indexed, "indexed_chapters", []) or []),
                    "status": getattr(indexed, "status", "completed" if indexed.failed_chapters == 0 else "partial"),
                    "no_chapters": bool(getattr(indexed, "no_chapters", False)),
                    "timings_ms": dict(getattr(indexed, "timings_ms", {}) or {}),
                }
                await self._save_task(task)
                if self._novel_repo is not None:
                    if task.status == "succeeded":
                        await self._novel_repo.update_book_status(
                            task.owner_scope,
                            task.book_id,
                            NovelStatus.READY,
                            progress=1.0,
                        )
                    else:
                        total = indexed.processed_chapters + indexed.skipped_chapters + indexed.failed_chapters
                        progress = (
                            (indexed.processed_chapters + indexed.skipped_chapters) / total
                            if total > 0
                            else 0.0
                        )
                        await self._novel_repo.update_book_status(
                            task.owner_scope,
                            task.book_id,
                            NovelStatus.EXTRACTING,
                            progress=min(0.99, max(0.0, progress)),
                            error_msg=str(indexed.errors or "partial index result")[:500],
                        )
                outcomes.append({"task_id": task.id, "status": task.status, "result": task.result})
            except Exception as exc:
                task.status = "failed"
                task.result = {"error": str(exc)[:500]}
                await self._save_task(task)
                if self._novel_repo is not None:
                    await self._novel_repo.update_book_status(
                        task.owner_scope,
                        task.book_id,
                        NovelStatus.ERROR,
                        error_msg=str(exc)[:500],
                    )
                outcomes.append({"task_id": task.id, "status": task.status, "result": task.result})
        return {"processed": len(outcomes), "tasks": outcomes}

    async def _requeue_stale_running_tasks(self, tasks: list[NovelAnalysisTask]) -> None:
        now = datetime.now(timezone.utc)
        for task in tasks:
            if task.status != "running" or not self._is_stale(task, now):
                continue
            task.status = "queued"
            task.result = {
                **(task.result if isinstance(task.result, dict) else {}),
                "requeued_after_restart": True,
            }
            await self._save_task(task)

    def _is_stale(self, task: NovelAnalysisTask, now: datetime) -> bool:
        created_at = getattr(task, "created_at", None)
        if created_at is None:
            return False
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                return False
        if not isinstance(created_at, datetime):
            return False
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return now - created_at.astimezone(timezone.utc) >= self._stale_running_after

    async def _save_task(self, task: NovelAnalysisTask):
        value = self._runtime_repo.save_task(task)
        return await self._resolve(value)

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
        scope = owner_scope
        try:
            books = await self._resolve(list_books(scope, limit=10000, offset=0))
        except TypeError:
            books = await self._resolve(list_books(scope, limit=10000))
        active_by_book = {
            (str(task.owner_scope), int(task.book_id))
            for task in tasks
            if task.book_id is not None and task.status in {"queued", "pending", "running"}
        }
        completed_repairs = {
            (str(task.owner_scope), int(task.book_id))
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
            book_scope = owner_scope or str(getattr(book, "owner_scope", "legacy") or "legacy")
            book_id = int(book.id)
            book_key = (book_scope, book_id)
            if book_key in active_by_book:
                continue
            reason = await self._repair_reason(book_scope, book)
            if reason is None:
                continue
            if book_key in completed_repairs and reason == "zero_statistics":
                # A completed repair may legitimately find no named entity in
                # a short chapter.  Do not enqueue it on every scheduler tick.
                continue
            task = await self._create_repair_task(book_scope, book, reason)
            if task is None:
                continue
            tasks.append(task)
            active_by_book.add(book_key)
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


async def run_novel_index_worker(*, index_service, runtime_repo, novel_repo=None, limit: int = 10, owner_scope: str | None = None):
    return await NovelIndexWorker(index_service=index_service, runtime_repo=runtime_repo, novel_repo=novel_repo).run(
        limit=limit,
        owner_scope=owner_scope,
    )
