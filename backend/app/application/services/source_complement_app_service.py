from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.domain.services.source_complement import (
    SourceComplementService,
    SourceFetchResult,
)


class SourceComplementAppService:
    def __init__(self, repo, fetcher, max_concurrent: int = 5):
        self._repo = repo
        self._fetcher = fetcher
        self._max_concurrent = max_concurrent

    async def complement_chapter_candidates(
        self,
        book_name: str,
        chapter_title: str,
        chapter_num: int,
        items: list[dict[str, Any]],
        reference_content: str = "",
        merge_strategy: str = "hybrid",
    ) -> dict[str, Any]:
        source_ids = sorted({int(item["source_id"]) for item in items if item.get("source_id") is not None})
        sources = await self._repo.list_book_sources_full(ids=source_ids)
        source_map = {source["id"]: source for source in sources}

        candidates: dict[str, dict[str, Any]] = {}
        candidate_ids: list[str] = []
        for item in items:
            source_id = int(item["source_id"])
            source = source_map.get(source_id)
            if not source:
                continue
            chapter_url = item["chapter_url"]
            candidate_id = f"{source_id}::{chapter_url}"
            candidates[candidate_id] = {
                "source": source,
                "source_name": item.get("source_name") or source.get("bookSourceName", ""),
                "source_url": item.get("source_url") or source.get("bookSourceUrl", ""),
                "chapter_url": chapter_url,
            }
            candidate_ids.append(candidate_id)

        async def fetch_fn(candidate_id: str, chapter_info: dict[str, Any]) -> SourceFetchResult:
            candidate = candidates[candidate_id]
            source = candidate["source"]
            content = await self._fetcher.get_content(source, candidate["chapter_url"])
            body = content.get("content", "") or ""
            return SourceFetchResult(
                source_url=candidate["source_url"],
                source_name=candidate["source_name"],
                success=bool(body),
                content=body,
                word_count=len(body),
                chapter_title=content.get("title") or chapter_info.get("chapter_title", ""),
                chapter_num=chapter_info.get("chapter_num", 0),
                error=None if body else "empty content",
            )

        service = SourceComplementService(
            fetch_fn=fetch_fn,
            max_concurrent=self._max_concurrent,
            merge_strategy=merge_strategy,
        )
        result = await service.complement_chapter(
            book_name=book_name,
            chapter_title=chapter_title,
            chapter_num=chapter_num,
            source_urls=candidate_ids,
            reference_content=reference_content,
            publish_events=False,
        )

        payload = asdict(result)
        payload["source_results"] = [asdict(item) for item in result.source_results]
        return payload

    async def aclose(self) -> None:
        close = getattr(self._fetcher, "close", None)
        if close is not None:
            await close()
