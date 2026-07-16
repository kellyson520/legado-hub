from abc import ABC, abstractmethod

from app.domain.entities.ai_runtime import AITask


class AIRuntimeRepository(ABC):
    @abstractmethod
    def save_task(self, task: AITask) -> AITask:
        raise NotImplementedError

    @abstractmethod
    def list_tasks(self) -> list[AITask]:
        raise NotImplementedError

    @abstractmethod
    def list_tasks_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> tuple[list[AITask], int]:
        raise NotImplementedError
