from abc import ABC, abstractmethod
from datetime import datetime


class SourceRepository(ABC):
    @abstractmethod
    async def list_book_sources(
        self, page: int, page_size: int, enabled_only: bool = False
    ) -> tuple[list[dict], int]:
        raise NotImplementedError

    @abstractmethod
    async def create_book_source(self, data: dict, actor_id: int) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def update_book_source(self, source_id: int, data: dict, actor_id: int) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def delete_book_source(self, source_id: int, actor_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_groups(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def export_book_sources(self, enabled_only: bool = False) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def health_snapshot(self) -> dict:
        raise NotImplementedError

    async def upsert_book_sources(self, items: list[dict], actor_id: int) -> int:
        raise NotImplementedError

    async def upsert_runtime_book_sources(self, items: list[dict], actor_id: int) -> int:
        raise NotImplementedError

    @abstractmethod
    async def create_ephemeral_book_sources(self, items: list[dict], tenant_id: str) -> list[int]:
        """Materialize sources in a tenant-scoped, expiring runtime sandbox."""
        raise NotImplementedError

    @abstractmethod
    async def list_ephemeral_book_sources(
        self,
        tenant_id: str,
        *,
        ids: list[int] | None = None,
        urls: list[str] | None = None,
    ) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def delete_ephemeral_book_sources(self, tenant_id: str, ids: list[int]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_expired_ephemeral_book_sources(
        self,
        *,
        now: datetime | None = None,
        tenant_id: str | None = None,
    ) -> int:
        raise NotImplementedError

    async def list_book_sources_full(
        self,
        enabled_only: bool = False,
        ids: list[int] | None = None,
        urls: list[str] | None = None,
    ) -> list[dict]:
        raise NotImplementedError

    async def update_book_source_health_fields(
        self,
        source_id: int,
        source_status: str,
        error_msg: str,
        last_check_time,
    ) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def disable_stale_sources(self, cutoff: datetime, limit: int = 100) -> list[dict]:
        """Disable enabled sources that have been in an error state since cutoff."""
        raise NotImplementedError
