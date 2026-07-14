from __future__ import annotations

import time
from typing import Any


REAL_SITE_URLS = [
    "https://www.biquga.com/list/0/1.html",
    "https://www.beiquge.com/rank/",
    "https://m.biqugen.com/",
    "https://www.bqg39.cc/",
]


class SourceToInsightAcceptanceService:
    def __init__(
        self,
        *,
        source_build_service,
        source_build_runtime=None,
        reading_service=None,
        complement_service=None,
        character_service=None,
        knowledge_service=None,
        provider_platform=None,
        job_repository=None,
    ):
        self._source_build_service = source_build_service
        self._source_build_runtime = source_build_runtime
        self._reading_service = reading_service
        self._complement_service = complement_service
        self._character_service = character_service
        self._knowledge_service = knowledge_service
        self._provider_platform = provider_platform
        self._job_repository = job_repository

    async def run(self, scenario: dict[str, Any]) -> dict[str, Any]:
        started = time.time()
        source_urls = list(scenario.get("source_urls") or REAL_SITE_URLS)
        tenant_id = str(scenario.get("tenant_id") or "source-insight-smoke")
        book_name = str(scenario.get("book_name") or "斗罗大陆")
        author_hint = str(scenario.get("author_hint") or "唐家三少")

        steps: list[dict[str, Any]] = []
        source_builds = []
        build_started = time.time()
        for url in source_urls:
            source_builds.append(self._run_source_build(url=url, tenant_id=tenant_id, keyword=book_name))
        steps.append({
            "name": "source_build",
            "status": "passed" if any(item["status"] == "passed" for item in source_builds) else "failed",
            "elapsed_ms": _elapsed_ms(build_started),
            "summary": {
                "total": len(source_builds),
                "passed": sum(1 for item in source_builds if item["status"] == "passed"),
                "failed": sum(1 for item in source_builds if item["status"] == "failed"),
            },
            "errors": [item["error"] for item in source_builds if item.get("error")],
        })

        usable_builds = [
            item for item in source_builds
            if item.get("status") == "passed" and item.get("decision") in {"canary", None}
        ]
        book_candidates = []
        toc_candidates = []
        chapter_candidates = []
        complement = {}
        insights = {"characters": [], "relations": [], "plot_events": [], "world_rules": [], "timeline": []}

        if self._reading_service is not None and usable_builds:
            search_result = await self._reading_service.search_books(
                book_name,
                source_ids=None,
                limit_per_source=3,
                author_hint=author_hint,
                routing_mode="auto",
                include_health=True,
            )
            book_candidates = search_result.get("items", [])
            selected = book_candidates[: min(3, len(book_candidates))]
            for book in selected:
                toc = await self._reading_service.get_book_toc(
                    book["source_id"],
                    book["bookUrl"],
                    book_name=book_name,
                    author_hint=author_hint,
                    routing_mode="auto",
                )
                toc_candidates.append(toc)
                chapters = toc.get("chapters") or []
                if not chapters:
                    continue
                chapter = _select_chapter(
                    chapters,
                    int(scenario.get("chapter_index", 0) or 0),
                    str(scenario.get("chapter_title") or ""),
                )
                content = await self._reading_service.get_chapter_content(
                    book["source_id"],
                    chapter["url"],
                    book_name=book_name,
                    author_hint=author_hint,
                    chapter_title=chapter.get("title"),
                    chapter_index=chapter.get("index"),
                    routing_mode="auto",
                )
                chapter_candidates.append({
                    **content,
                    "content_preview": _preview(content.get("content", "")),
                    "content_length": len(content.get("content", "") or ""),
                })

        if self._complement_service is not None and chapter_candidates:
            items = [
                {
                    "source_id": item["source_id"],
                    "chapter_url": item["chapter_url"],
                    "source_name": "",
                    "source_url": "",
                }
                for item in chapter_candidates
            ]
            try:
                complement = await self._complement_service.complement_chapter_candidates(
                    book_name=book_name,
                    chapter_title=chapter_candidates[0].get("title") or str(scenario.get("chapter_title") or ""),
                    chapter_num=int(scenario.get("chapter_index", 0) or 0) + 1,
                    items=items,
                    reference_content=chapter_candidates[0].get("content", ""),
                    merge_strategy="hybrid",
                )
            finally:
                close = getattr(self._complement_service, "aclose", None)
                if close:
                    await close()

        if self._character_service is not None:
            character_result = await self._character_service.calibrate(
                keyword=book_name,
                items=[
                    {
                        "source_id": item.get("source_id"),
                        "name": book_name,
                        "author": author_hint,
                        "excerpt": item.get("content_preview", ""),
                    }
                    for item in chapter_candidates
                ],
                actor_id=tenant_id,
            )
            insights["characters"] = character_result.get("items", [])

        status = "passed" if steps[-1]["summary"]["passed"] == len(source_urls) else "partial"
        if steps[-1]["summary"]["passed"] == 0:
            status = "failed"
        return {
            "scenario": {
                "source_urls": source_urls,
                "book_name": book_name,
                "author_hint": author_hint,
                "chapter_index": int(scenario.get("chapter_index", 0) or 0),
                "chapter_title": str(scenario.get("chapter_title") or "第一章"),
                "use_ai": bool(scenario.get("use_ai", False)),
            },
            "status": status,
            "elapsed_ms": _elapsed_ms(started),
            "steps": steps,
            "source_builds": source_builds,
            "book_candidates": book_candidates,
            "toc_candidates": toc_candidates,
            "chapter_candidates": chapter_candidates,
            "complement": complement,
            "insights": insights,
            "knowledge_proposals": [],
            "ai": {"used": False, "status": "skipped", "provider": "", "model": "", "usage": {}},
        }

    def _run_source_build(self, *, url: str, tenant_id: str, keyword: str) -> dict[str, Any]:
        started = time.time()
        try:
            submission = self._source_build_service.submit(
                tenant_id=tenant_id,
                url=url,
                keyword=keyword,
            )
            runtime_result = {}
            if self._source_build_runtime is not None:
                if self._job_repository is not None and hasattr(self._source_build_runtime, "handle_job"):
                    job = self._job_repository.get_job(submission.job_id)
                    runtime_result = self._source_build_runtime.handle_job(job)
                elif hasattr(self._source_build_runtime, "handle_source_version"):
                    runtime_result = self._source_build_runtime.handle_source_version(
                        source_version_id=submission.source_version_id,
                        job_id=submission.job_id,
                        url=submission.normalized_url,
                        tenant_id=tenant_id,
                    )
            return {
                "url": url,
                "normalized_url": submission.normalized_url,
                "job_id": submission.job_id,
                "source_version_id": submission.source_version_id,
                "source_version_status": submission.source_version_status,
                "status": "passed",
                "elapsed_ms": _elapsed_ms(started),
                "agent_run_id": runtime_result.get("agent_run_id"),
                "decision": runtime_result.get("decision"),
                "strategy": runtime_result.get("strategy"),
                "review_required": runtime_result.get("review_required"),
                "source_rule": runtime_result.get("source_rule") or {},
                "autonomous_build": runtime_result.get("autonomous_build") or {},
                "error": "",
            }
        except Exception as exc:
            return {
                "url": url,
                "status": "failed",
                "elapsed_ms": _elapsed_ms(started),
                "error": str(exc) or exc.__class__.__name__,
            }


def _elapsed_ms(started: float) -> int:
    return int((time.time() - started) * 1000)


def _select_chapter(chapters: list[dict[str, Any]], chapter_index: int, chapter_title: str) -> dict[str, Any]:
    for item in chapters:
        if int(item.get("index", -1)) == chapter_index:
            return item
    if chapter_title:
        for item in chapters:
            if chapter_title in str(item.get("title", "")):
                return item
    return chapters[0]


def _preview(text: str, limit: int = 240) -> str:
    text = (text or "").strip()
    return text[:limit]
