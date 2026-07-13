from abc import ABC, abstractmethod

from app.domain.entities.novel_runtime import NovelAnalysisTask, NovelIngestion


class NovelRuntimeRepository(ABC):
    @abstractmethod
    def save_ingestion(self, ingestion: NovelIngestion) -> NovelIngestion:
        raise NotImplementedError

    @abstractmethod
    def list_ingestions(self) -> list[NovelIngestion]:
        raise NotImplementedError

    @abstractmethod
    def get_ingestion(self, novel_id: str) -> NovelIngestion | None:
        raise NotImplementedError

    @abstractmethod
    def save_task(self, task: NovelAnalysisTask) -> NovelAnalysisTask:
        raise NotImplementedError

    @abstractmethod
    def list_tasks(self) -> list[NovelAnalysisTask]:
        raise NotImplementedError
