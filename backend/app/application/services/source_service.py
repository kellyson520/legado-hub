from pathlib import Path

from app.core.pagination import paginated_result
from app.domain.repositories.source_repo import SourceRepository
from app.services.fetcher import SourceFetcher


class SourceAppService:
    def __init__(self, repo: SourceRepository):
        self._repo = repo

    async def list_book_sources(self, page: int, page_size: int, enabled_only: bool = False) -> dict:
        items, total = await self._repo.list_book_sources(page=page, page_size=page_size, enabled_only=enabled_only)
        return paginated_result(items, page=page, page_size=page_size, total=total)

    async def create_book_source(self, payload: dict, actor_id: int) -> dict:
        return await self._repo.create_book_source(payload, actor_id)

    async def update_book_source(self, source_id: int, payload: dict, actor_id: int) -> dict:
        return await self._repo.update_book_source(source_id, payload, actor_id)

    async def delete_book_source(self, source_id: int, actor_id: int) -> None:
        await self._repo.delete_book_source(source_id, actor_id)

    async def export_book_sources(self, enabled_only: bool = False) -> dict:
        items = await self._repo.export_book_sources(enabled_only=enabled_only)
        return {"items": items, "count": len(items)}

    async def import_book_sources_from_file(self, file_path: str, actor_id: int, replace_existing: bool = True) -> dict:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        parser = SourceFetcher()
        book_sources, _ = parser.parse_sources_from_text(text, origin=str(path))
        items_to_import = book_sources
        if not replace_existing:
            existing = await self._repo.list_book_sources_full(urls=[item["bookSourceUrl"] for item in book_sources])
            existing_urls = {item["bookSourceUrl"] for item in existing}
            items_to_import = [item for item in book_sources if item["bookSourceUrl"] not in existing_urls]
        count = await self._repo.upsert_book_sources(items_to_import, actor_id)
        return {"file_path": str(path), "book_count": count}
