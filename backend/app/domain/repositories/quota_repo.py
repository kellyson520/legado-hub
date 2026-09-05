from abc import ABC, abstractmethod


class QuotaUsageRepository(ABC):
    @abstractmethod
    async def upsert_max_usage(
        self,
        *,
        api_key_id: int,
        date: str,
        fetch_count: int,
        ai_chars: int,
        storage_mb: float,
    ) -> None:
        """Persist the maximum observed usage for a key/day."""
        raise NotImplementedError
