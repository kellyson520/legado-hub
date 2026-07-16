from abc import ABC, abstractmethod

from app.domain.entities.source_runtime import (
    SourceDefinition,
    SourceDeployment,
    SourceHealthEvent,
    SourceTestRun,
    SourceVersion,
)


class SourceRuntimeRepository(ABC):
    @abstractmethod
    def ensure_source_definition(
        self,
        source_type: str,
        source_key: str,
        source_name: str = "",
        source_group: str = "default",
    ) -> SourceDefinition:
        raise NotImplementedError

    @abstractmethod
    def create_candidate_version(
        self,
        source_type: str,
        source_id: str,
        payload: dict,
        created_by: str,
    ) -> SourceVersion:
        raise NotImplementedError

    @abstractmethod
    def existing_source_ids(self, source_type: str, source_ids: list[str]) -> set[str]:
        raise NotImplementedError

    @abstractmethod
    def create_candidate_version_ids_bulk(
        self,
        source_type: str,
        entries: list[tuple[str, dict, str]],
    ) -> dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def get_version(self, version_id: str) -> SourceVersion | None:
        raise NotImplementedError

    @abstractmethod
    def list_versions(self, source_type: str, source_id: str) -> list[SourceVersion]:
        raise NotImplementedError

    @abstractmethod
    def list_recent_versions(self, *, status: str | None = None, limit: int = 50) -> list[SourceVersion]:
        raise NotImplementedError

    @abstractmethod
    def list_visible_versions(
        self,
        actor_id: str,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[SourceVersion], int]:
        raise NotImplementedError

    @abstractmethod
    def list_published_versions(self) -> list[SourceVersion]:
        raise NotImplementedError

    @abstractmethod
    def record_test_run(
        self,
        source_version_id: str,
        trigger: str,
        score: int,
        grade: str,
        step_results: dict,
        diagnostics: list[str] | None = None,
    ) -> SourceTestRun:
        raise NotImplementedError

    @abstractmethod
    def list_test_runs(self, source_version_id: str | None = None) -> list[SourceTestRun]:
        raise NotImplementedError

    @abstractmethod
    def list_latest_test_runs(self, source_version_ids: list[str]) -> dict[str, SourceTestRun]:
        raise NotImplementedError

    @abstractmethod
    def record_deployment(
        self,
        source_version_id: str,
        action: str,
        status: str,
        quality_gate: dict,
        actor_id: str,
    ) -> SourceDeployment:
        raise NotImplementedError

    @abstractmethod
    def record_health_event(
        self,
        source_version_id: str,
        event_type: str,
        detail: dict,
    ) -> SourceHealthEvent:
        raise NotImplementedError

    @abstractmethod
    def update_version_status(self, version_id: str, status: str) -> SourceVersion:
        raise NotImplementedError

    @abstractmethod
    def update_version_payload(self, version_id: str, payload: dict) -> SourceVersion:
        raise NotImplementedError

    @abstractmethod
    def list_deployments(self, source_version_id: str | None = None) -> list[SourceDeployment]:
        raise NotImplementedError
