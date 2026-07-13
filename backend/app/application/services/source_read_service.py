import re

from app.core.exceptions import NotFoundException


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
        ranked_sources = [
            {
                "source": source,
                "decision": {
                    "health_status": "unknown",
                    "failure_reason": "",
                    "route_decision": "probe_only",
                    "route_score": 0,
                },
            }
            for source in sources
        ]
        if self._routing_service is not None:
            snapshot_map = self._routing_service.snapshot_map([source["id"] for source in sources])
            ranked_sources = self._routing_service.rank_search_sources(
                sources,
                snapshot_map,
                routing_mode=routing_mode,
            )

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
                items.append(
                    {
                        "source_id": source["id"],
                        "name": book.get("name", ""),
                        "author": book.get("author", ""),
                        "bookUrl": book.get("bookUrl", ""),
                        "sourceName": source["bookSourceName"],
                        "sourceUrl": source["bookSourceUrl"],
                    }
                )
                if include_health:
                    items[-1].update(
                        {
                            "health_status": decision["health_status"],
                            "failure_reason": decision["failure_reason"],
                            "route_decision": decision["route_decision"],
                            "route_score": decision["route_score"],
                        }
                    )
        return {
            "keyword": keyword,
            "items": items,
            "route_summary": {
                "selected_source_ids": selected_source_ids,
                "routing_mode": routing_mode,
                "include_health": include_health,
            },
        }

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

        candidates = await self._resolve_book_candidates(book_name, author_hint, routing_mode)
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

        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "book_url": book_url,
            "chapters": chapters,
            "fallback_used": False,
        }

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
            return {
                "source_id": source_id,
                "resolved_source_id": source_id,
                "chapter_url": chapter_url,
                "fallback_used": False,
                **content,
            }

        candidates = await self._resolve_book_candidates(book_name, author_hint, routing_mode)
        for candidate in candidates:
            if candidate["source"]["id"] == source_id:
                continue
            chapters = await self._fetcher.get_toc(candidate["source"], candidate["book"]["bookUrl"])
            match = None
            if chapter_index is not None:
                match = next(
                    (item for item in chapters if int(item.get("index", -1)) == chapter_index),
                    None,
                )
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

        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "chapter_url": chapter_url,
            "fallback_used": False,
            **content,
        }

    async def _get_source_or_raise(self, source_id: int) -> dict:
        sources = await self._repo.list_book_sources_full(ids=[source_id])
        if not sources:
            raise NotFoundException(f"book source not found: {source_id}")
        return sources[0]

    async def _resolve_book_candidates(
        self,
        book_name: str,
        author_hint: str | None,
        routing_mode: str,
    ) -> list[dict]:
        if self._routing_service is None:
            return []
        if hasattr(self._routing_service, "resolve_book_candidates"):
            return await self._routing_service.resolve_book_candidates(
                self._repo,
                book_name,
                author_hint,
                self._fetcher,
                routing_mode=routing_mode,
            )

        sources = await self._repo.list_book_sources_full(enabled_only=True)
        snapshot_map = self._routing_service.snapshot_map([source["id"] for source in sources])
        ranked = self._routing_service.rank_search_sources(
            sources,
            snapshot_map,
            routing_mode=routing_mode,
        )
        candidates = []
        for routed in ranked:
            source = routed["source"]
            results = await self._fetcher.search(source, book_name, page=1)
            if results:
                candidates.append(
                    {
                        "source": source,
                        "book": results[0],
                        "decision": routed["decision"],
                    }
                )
        return candidates

    @classmethod
    def _score_book_candidate(cls, keyword: str, author_hint: str | None, book: dict) -> int:
        keyword_norm = cls._normalize_text(keyword)
        name = book.get("name", "")
        author = book.get("author", "")
        name_norm = cls._normalize_text(name)
        author_norm = cls._normalize_text(author)

        score = 0
        if name_norm == keyword_norm:
            score += 120
        elif keyword_norm and keyword_norm in name_norm:
            score += 70
        elif name and keyword in name:
            score += 40

        if author:
            score += 5
        if book.get("bookUrl"):
            score += 5

        score -= min(abs(len(name_norm) - len(keyword_norm)), 20)

        if author_hint:
            author_hint_norm = cls._normalize_text(author_hint)
            if author_norm == author_hint_norm:
                score += 80
            elif author_hint_norm and (
                author_hint_norm in author_norm or author_norm in author_hint_norm
            ):
                score += 40

        return score

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[\W_]+", "", (value or "").lower())
