from abc import ABC, abstractmethod

from app.domain.entities.novel_runtime import NovelModelPreference


class NovelModelPreferenceRepository(ABC):
    """Persistence port for user/book/session/task model overrides."""

    @abstractmethod
    def save(self, preference: NovelModelPreference) -> NovelModelPreference:
        raise NotImplementedError

    @abstractmethod
    def get(
        self,
        owner_scope: str,
        scope_type: str,
        scope_id: str,
        task_type: str,
    ) -> NovelModelPreference | None:
        raise NotImplementedError

    @abstractmethod
    def delete(
        self,
        owner_scope: str,
        scope_type: str,
        scope_id: str,
        task_type: str,
    ) -> bool:
        raise NotImplementedError
