from abc import ABC, abstractmethod

from app.domain.entities.source_review import SourceReviewItem


class SourceReviewRepository(ABC):
    @abstractmethod
    def save_item(self, item: SourceReviewItem) -> SourceReviewItem:
        raise NotImplementedError

    @abstractmethod
    def get_item(self, item_id: str) -> SourceReviewItem | None:
        raise NotImplementedError

    @abstractmethod
    def list_items(
        self,
        *,
        status: str | None = None,
        review_type: str | None = None,
    ) -> list[SourceReviewItem]:
        raise NotImplementedError
