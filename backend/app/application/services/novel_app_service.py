from app.domain.entities.novel_runtime import NovelIngestion


class NovelAppService:
    def __init__(self, repo=None):
        self._repo = repo

    async def list_books(self) -> list[dict]:
        if self._repo is None:
            return []
        return [self._serialize(ingestion) for ingestion in self._repo.list_ingestions()]

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
