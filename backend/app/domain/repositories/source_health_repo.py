from abc import ABC, abstractmethod

from app.domain.entities.source_health import SourceHealthSnapshot, SourceProbeRun


class SourceHealthRepository(ABC):
    @abstractmethod
    def get_snapshot(self, source_id: int) -> SourceHealthSnapshot | None:
        raise NotImplementedError

    @abstractmethod
    def list_snapshots(
        self,
        statuses: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SourceHealthSnapshot], int]:
        raise NotImplementedError

    @abstractmethod
    def list_book_source_health_inventory(
        self,
        statuses: list[str] | None = None,
        search: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SourceHealthSnapshot], int]:
        raise NotImplementedError

    @abstractmethod
    def upsert_snapshot(self, snapshot: SourceHealthSnapshot) -> SourceHealthSnapshot:
        raise NotImplementedError

    @abstractmethod
    def record_probe_run(self, run: SourceProbeRun) -> SourceProbeRun:
        raise NotImplementedError

    @abstractmethod
    def list_probe_runs(self, source_id: int, limit: int = 20) -> list[SourceProbeRun]:
        raise NotImplementedError

    def list_probe_candidate_ids(self, limit: int = 20) -> list[int]:
        raise NotImplementedError
