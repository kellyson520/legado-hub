from __future__ import annotations

from datetime import datetime

from app.application.ports.quota import QuotaStore
from app.core.logging import get_logger
from app.domain.repositories.auth_repo import AuthRepository
from app.domain.repositories.quota_repo import QuotaUsageRepository
from app.domain.repositories.source_repo import SourceRepository


logger = get_logger("maintenance")
_QUOTA_METRICS = ("fetch_count", "ai_chars", "storage_mb")


class MaintenanceService:
    """Application use cases for scheduled maintenance.

    Scheduling is an adapter concern. This service owns the use-case boundary,
    while repositories and the quota store hide SQLite/Redis details from the
    scheduler.
    """

    def __init__(
        self,
        *,
        source_repo: SourceRepository,
        auth_repo: AuthRepository,
        quota_repo: QuotaUsageRepository,
        quota_store: QuotaStore,
    ):
        self._source_repo = source_repo
        self._auth_repo = auth_repo
        self._quota_repo = quota_repo
        self._quota_store = quota_store

    async def disable_stale_sources(self, *, cutoff: datetime, limit: int = 100) -> list[dict]:
        return await self._source_repo.disable_stale_sources(cutoff, limit=limit)

    async def reset_daily_quotas(self) -> int:
        keys = await self._auth_repo.list_enabled_api_keys()
        for key in keys:
            for metric in _QUOTA_METRICS:
                await self._quota_store.reset_quota(key.id, metric)
        return len(keys)

    async def sync_quotas(self, *, date: str) -> int:
        keys = await self._auth_repo.list_enabled_api_keys()
        synced = 0
        for key in keys:
            values = {
                metric: await self._quota_store.get_quota(key.id, metric)
                for metric in _QUOTA_METRICS
            }
            if not any(value > 0 for value in values.values()):
                continue
            await self._quota_repo.upsert_max_usage(
                api_key_id=key.id,
                date=date,
                fetch_count=int(values["fetch_count"]),
                ai_chars=int(values["ai_chars"]),
                storage_mb=float(values["storage_mb"]),
            )
            synced += 1
        logger.info(
            "配额同步完成",
            extra={"action": "quota_sync", "date": date, "synced": synced},
        )
        return synced
