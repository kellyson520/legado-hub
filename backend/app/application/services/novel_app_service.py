from app.domain.entities.novel_runtime import NovelIngestion
from app.core.pagination import pagination_meta


class NovelAppService:
    def __init__(self, repo=None):
        self._repo = repo

    async def list_books(self) -> list[dict]:
        if self._repo is None:
            return []
        return [self._serialize(ingestion) for ingestion in self._repo.list_ingestions()]

    async def list_books_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> dict:
        if hasattr(self._repo, "list_ingestions_page"):
            rows, total = self._repo.list_ingestions_page(
                page=page,
                page_size=page_size,
                search=search,
                status=status,
            )
        else:
            all_rows = self._repo.list_ingestions()
            normalized = search.strip().lower()
            filtered = [
                item for item in all_rows
                if (not normalized or normalized in f"{item.id} {item.title} {item.provider} {item.pipeline}".lower())
                and (not status or item.status == status)
            ]
            total = len(filtered)
            rows = filtered[(page - 1) * page_size : page * page_size]
        return {
            "items": [self._serialize(item) for item in rows],
            "meta": pagination_meta(page, page_size, total, search=search, status=status),
        }

    @staticmethod
    def _serialize(ingestion: NovelIngestion) -> dict:
        return {
            "id": ingestion.id,
            "title": ingestion.title,
            "status": ingestion.status,
            "provider": ingestion.provider,
            "pipeline": ingestion.pipeline,
            "created_at": ingestion.created_at.isoformat(),
        }
