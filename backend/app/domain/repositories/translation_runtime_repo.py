from abc import ABC, abstractmethod

from app.domain.entities.translation_runtime import TranslationJob


class TranslationRuntimeRepository(ABC):
    @abstractmethod
    def save_job(self, job: TranslationJob) -> TranslationJob:
        raise NotImplementedError

    @abstractmethod
    def list_jobs(self) -> list[TranslationJob]:
        raise NotImplementedError

    @abstractmethod
    def get_job(self, job_id: str) -> TranslationJob | None:
        raise NotImplementedError

    @abstractmethod
    def update_job_review(self, job_id: str, *, review_status: str, memory_payload: dict) -> TranslationJob:
        raise NotImplementedError
