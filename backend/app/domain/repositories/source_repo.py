from abc import ABC, abstractmethod


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
