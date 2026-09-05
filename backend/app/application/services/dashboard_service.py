from app.domain.repositories.source_repo import SourceRepository


class DashboardService:
    def __init__(self, repo: SourceRepository):
        self._repo = repo

    async def get_dashboard(self) -> dict:
        snapshot = await self._repo.health_snapshot()
        return {
            "book_sources": snapshot["book_sources_total"],
            "rss_sources": snapshot["rss_sources_total"],
            "subscriptions": snapshot["subscriptions_total"],
            "filter_rules": snapshot["filter_rules_total"],
        }

    async def get_groups(self) -> list[dict]:
        return await self._repo.list_groups()

    async def get_health(self) -> dict:
        return await self._repo.health_snapshot()
