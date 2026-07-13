from abc import ABC, abstractmethod

from app.domain.entities.ai_runtime import AITask


class AIRuntimeRepository(ABC):
    @abstractmethod
    def save_task(self, task: AITask) -> AITask:
        raise NotImplementedError

    @abstractmethod
    def list_tasks(self) -> list[AITask]:
        raise NotImplementedError
