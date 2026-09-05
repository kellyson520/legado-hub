from app.infrastructure.persistence.sqlite.session import SessionLocal
from app.domain.entities.evidence import EvidenceSpan

from .schema import EvidenceSpanModel


class SQLiteEvidenceRepository:
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db) -> None:
        if self._session is None:
            db.close()

    @staticmethod
    def _entity(model: EvidenceSpanModel) -> EvidenceSpan:
        return EvidenceSpan(
            id=model.id,
            canonical_chapter_id=model.canonical_chapter_id,
            content_variant_id=model.content_variant_id,
            start_offset=model.start_offset,
            end_offset=model.end_offset,
            excerpt=model.excerpt,
            excerpt_sha256=model.excerpt_sha256,
            content_sha256=model.content_sha256,
            created_at=model.created_at,
        )

    def create_spans(self, spans: list[EvidenceSpan]) -> list[EvidenceSpan]:
        if not spans:
            return []
        db = self._db()
        try:
            models = [
                EvidenceSpanModel(
                    id=span.id,
                    canonical_chapter_id=span.canonical_chapter_id,
                    content_variant_id=span.content_variant_id,
                    start_offset=span.start_offset,
                    end_offset=span.end_offset,
                    excerpt=span.excerpt,
                    excerpt_sha256=span.excerpt_sha256,
                    content_sha256=span.content_sha256,
                )
                for span in spans
            ]
            db.add_all(models)
            db.commit()
            for model in models:
                db.refresh(model)
            return [self._entity(model) for model in models]
        finally:
            self._close(db)

    def get_span(self, span_id: str) -> EvidenceSpan | None:
        db = self._db()
        try:
            model = db.query(EvidenceSpanModel).filter(EvidenceSpanModel.id == span_id).first()
            return self._entity(model) if model is not None else None
        finally:
            self._close(db)

    def list_spans_for_chapter(self, canonical_chapter_id: str, limit: int = 20) -> list[EvidenceSpan]:
        db = self._db()
        try:
            models = (
                db.query(EvidenceSpanModel)
                .filter(EvidenceSpanModel.canonical_chapter_id == canonical_chapter_id)
                .order_by(EvidenceSpanModel.start_offset.asc())
                .limit(limit)
                .all()
            )
            return [self._entity(model) for model in models]
        finally:
            self._close(db)

    def list_spans_for_variant(self, content_variant_id: str) -> list[EvidenceSpan]:
        db = self._db()
        try:
            models = (
                db.query(EvidenceSpanModel)
                .filter(EvidenceSpanModel.content_variant_id == content_variant_id)
                .order_by(EvidenceSpanModel.start_offset.asc())
                .all()
            )
            return [self._entity(model) for model in models]
        finally:
            self._close(db)
