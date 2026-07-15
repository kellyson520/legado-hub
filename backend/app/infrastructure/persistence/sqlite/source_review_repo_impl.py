import json

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.domain.entities.source_review import SourceReviewItem
from app.domain.repositories.source_review_repo import SourceReviewRepository

from .schema import SourceReviewItemModel


class SQLiteSourceReviewRepository(SourceReviewRepository):
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    @staticmethod
    def _entity(model: SourceReviewItemModel) -> SourceReviewItem:
        return SourceReviewItem(
            id=model.id,
            review_type=model.review_type,
            source_version_id=model.source_version_id,
            source_url=model.source_url,
            summary=model.summary,
            payload=json.loads(model.payload_json) if model.payload_json else {},
            status=model.status,
            created_by=model.created_by,
            reviewed_by=model.reviewed_by,
            created_at=model.created_at,
            resolved_at=model.resolved_at,
        )

    def save_item(self, item: SourceReviewItem) -> SourceReviewItem:
        db = self._db()
        try:
            model = db.query(SourceReviewItemModel).filter(SourceReviewItemModel.id == item.id).first()
            if model is None:
                model = SourceReviewItemModel(id=item.id)
                db.add(model)

            model.review_type = item.review_type
            model.source_version_id = item.source_version_id
            model.source_url = item.source_url
            model.summary = item.summary
            model.payload_json = json.dumps(item.payload, ensure_ascii=False)
            model.status = item.status
            model.created_by = item.created_by
            model.reviewed_by = item.reviewed_by
            model.created_at = item.created_at
            model.resolved_at = item.resolved_at

            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                existing = db.query(SourceReviewItemModel).filter(SourceReviewItemModel.id == item.id).first()
                if existing is None:
                    raise
                return self._entity(existing)
            db.refresh(model)
            return self._entity(model)
        finally:
            self._close(db)

    def get_item(self, item_id: str) -> SourceReviewItem | None:
        db = self._db()
        try:
            model = db.query(SourceReviewItemModel).filter(SourceReviewItemModel.id == item_id).first()
            return self._entity(model) if model else None
        finally:
            self._close(db)

    def list_items(
        self,
        *,
        status: str | None = None,
        review_type: str | None = None,
    ) -> list[SourceReviewItem]:
        db = self._db()
        try:
            query = db.query(SourceReviewItemModel)
            if status is not None:
                query = query.filter(SourceReviewItemModel.status == status)
            if review_type is not None:
                query = query.filter(SourceReviewItemModel.review_type == review_type)
            rows = (
                query.order_by(SourceReviewItemModel.created_at.desc(), SourceReviewItemModel.id.desc())
                .all()
            )
            return [self._entity(row) for row in rows]
        finally:
            self._close(db)
