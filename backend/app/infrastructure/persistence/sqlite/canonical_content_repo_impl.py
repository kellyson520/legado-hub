import json
from uuid import uuid4

from app.infrastructure.persistence.sqlite.session import SessionLocal
from app.domain.entities.canonical_content import (
    CanonicalChapter,
    CanonicalWork,
    ChapterAlignment,
    ContentVariant,
    RouteDecision,
    SourceChapter,
    SourceWork,
)

from .schema import (
    CanonicalChapterModel,
    CanonicalWorkModel,
    ChapterAlignmentModel,
    ContentVariantModel,
    RouteDecisionModel,
    SourceChapterModel,
    SourceWorkModel,
    WorkAliasModel,
)


def _loads_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


class SQLiteCanonicalContentRepository:
    def __init__(self, session=None):
        self._session = session

    def _db(self):
        return self._session or SessionLocal()

    def _close(self, db):
        if self._session is None:
            db.close()

    @staticmethod
    def _work_entity(model: CanonicalWorkModel) -> CanonicalWork:
        return CanonicalWork(
            id=model.id,
            title=model.title,
            author=model.author,
            normalized_title=model.normalized_title,
            normalized_author=model.normalized_author,
            created_at=model.created_at,
        )

    @staticmethod
    def _source_work_entity(model: SourceWorkModel) -> SourceWork:
        return SourceWork(
            id=model.id,
            canonical_work_id=model.canonical_work_id,
            source_id=model.source_id,
            title=model.title,
            author=model.author,
            normalized_title=model.normalized_title,
            normalized_author=model.normalized_author,
            created_at=model.created_at,
        )

    @staticmethod
    def _canonical_chapter_entity(model: CanonicalChapterModel) -> CanonicalChapter:
        return CanonicalChapter(
            id=model.id,
            canonical_work_id=model.canonical_work_id,
            chapter_index=model.chapter_index,
            title=model.title,
            normalized_title=model.normalized_title,
            created_at=model.created_at,
        )

    @staticmethod
    def _source_chapter_entity(model: SourceChapterModel) -> SourceChapter:
        return SourceChapter(
            id=model.id,
            source_work_id=model.source_work_id,
            chapter_index=model.chapter_index,
            title=model.title,
            chapter_url=model.chapter_url,
            canonical_chapter_id=model.canonical_chapter_id,
            normalized_title=model.normalized_title,
            created_at=model.created_at,
        )

    @staticmethod
    def _alignment_entity(model: ChapterAlignmentModel) -> ChapterAlignment:
        return ChapterAlignment(
            id=model.id,
            canonical_chapter_id=model.canonical_chapter_id,
            source_chapter_id=model.source_chapter_id,
            confidence=model.confidence,
            evidence=_loads_dict(model.evidence),
            review_status=model.review_status,
            created_at=model.created_at,
        )

    @staticmethod
    def _variant_entity(model: ContentVariantModel) -> ContentVariant:
        return ContentVariant(
            id=model.id,
            canonical_chapter_id=model.canonical_chapter_id,
            source_chapter_id=model.source_chapter_id,
            source_id=model.source_id,
            content=model.content,
            health_status=model.health_status,
            quality_score=model.quality_score,
            coverage_score=model.coverage_score,
            freshness_score=model.freshness_score,
            latency_ms=model.latency_ms,
            is_verified=model.is_verified,
            created_at=model.created_at,
        )

    @staticmethod
    def _route_entity(model: RouteDecisionModel) -> RouteDecision:
        return RouteDecision(
            id=model.id,
            tenant_id=model.tenant_id,
            canonical_chapter_id=model.canonical_chapter_id,
            selected_variant_id=model.selected_variant_id,
            fallback_count=model.fallback_count,
            route_summary=_loads_dict(model.route_summary),
            created_at=model.created_at,
        )

    def create_canonical_work(self, *, title: str, author: str) -> CanonicalWork:
        db = self._db()
        try:
            normalized_title = self._normalize(title)
            normalized_author = self._normalize(author)
            model = (
                db.query(CanonicalWorkModel)
                .filter(
                    CanonicalWorkModel.normalized_title == normalized_title,
                    CanonicalWorkModel.normalized_author == normalized_author,
                )
                .first()
            )
            if model is None:
                model = CanonicalWorkModel(
                    id=uuid4().hex,
                    title=title,
                    author=author,
                    normalized_title=normalized_title,
                    normalized_author=normalized_author,
                )
                db.add(model)
                db.commit()
                db.refresh(model)
            return self._work_entity(model)
        finally:
            self._close(db)

    def add_alias(self, canonical_work_id: str, *, alias: str, alias_type: str) -> None:
        db = self._db()
        try:
            existing = (
                db.query(WorkAliasModel)
                .filter(
                    WorkAliasModel.canonical_work_id == canonical_work_id,
                    WorkAliasModel.alias == alias,
                    WorkAliasModel.alias_type == alias_type,
                )
                .first()
            )
            if existing is None:
                db.add(WorkAliasModel(canonical_work_id=canonical_work_id, alias=alias, alias_type=alias_type))
                db.commit()
        finally:
            self._close(db)

    def list_works(self) -> list[CanonicalWork]:
        db = self._db()
        try:
            rows = db.query(CanonicalWorkModel).order_by(CanonicalWorkModel.created_at.asc()).all()
            return [self._work_entity(row) for row in rows]
        finally:
            self._close(db)

    def get_work(self, work_id: str) -> CanonicalWork | None:
        db = self._db()
        try:
            model = db.query(CanonicalWorkModel).filter(CanonicalWorkModel.id == work_id).first()
            return self._work_entity(model) if model else None
        finally:
            self._close(db)

    def create_source_work(self, *, canonical_work_id: str, source_id: str, title: str, author: str) -> SourceWork:
        db = self._db()
        try:
            model = SourceWorkModel(
                id=uuid4().hex,
                canonical_work_id=canonical_work_id,
                source_id=source_id,
                title=title,
                author=author,
                normalized_title=self._normalize(title),
                normalized_author=self._normalize(author),
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._source_work_entity(model)
        finally:
            self._close(db)

    def add_canonical_chapter(self, *, canonical_work_id: str, chapter_index: int, title: str) -> CanonicalChapter:
        db = self._db()
        try:
            model = CanonicalChapterModel(
                id=uuid4().hex,
                canonical_work_id=canonical_work_id,
                chapter_index=chapter_index,
                title=title,
                normalized_title=self._normalize(title),
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._canonical_chapter_entity(model)
        finally:
            self._close(db)

    def list_canonical_chapters(self, canonical_work_id: str) -> list[CanonicalChapter]:
        db = self._db()
        try:
            rows = (
                db.query(CanonicalChapterModel)
                .filter(CanonicalChapterModel.canonical_work_id == canonical_work_id)
                .order_by(CanonicalChapterModel.chapter_index.asc())
                .all()
            )
            return [self._canonical_chapter_entity(row) for row in rows]
        finally:
            self._close(db)

    def get_canonical_chapter(self, chapter_id: str) -> CanonicalChapter | None:
        db = self._db()
        try:
            model = db.query(CanonicalChapterModel).filter(CanonicalChapterModel.id == chapter_id).first()
            return self._canonical_chapter_entity(model) if model else None
        finally:
            self._close(db)

    def add_source_chapter(
        self,
        *,
        source_work_id: str,
        chapter_index: int,
        title: str,
        chapter_url: str,
        canonical_chapter_id: str | None = None,
    ) -> SourceChapter:
        db = self._db()
        try:
            model = SourceChapterModel(
                id=uuid4().hex,
                source_work_id=source_work_id,
                canonical_chapter_id=canonical_chapter_id,
                chapter_index=chapter_index,
                title=title,
                normalized_title=self._normalize(title),
                chapter_url=chapter_url,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._source_chapter_entity(model)
        finally:
            self._close(db)

    def save_alignment(
        self,
        *,
        canonical_chapter_id: str,
        source_chapter_id: str,
        confidence: float,
        evidence: dict,
        review_status: str,
    ) -> ChapterAlignment:
        db = self._db()
        try:
            model = ChapterAlignmentModel(
                id=uuid4().hex,
                canonical_chapter_id=canonical_chapter_id,
                source_chapter_id=source_chapter_id,
                confidence=confidence,
                evidence=json.dumps(evidence, ensure_ascii=False),
                review_status=review_status,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._alignment_entity(model)
        finally:
            self._close(db)

    def add_content_variant(
        self,
        *,
        canonical_chapter_id: str,
        source_chapter_id: str,
        source_id: str,
        content: str,
        health_status: str,
        quality_score: float,
        coverage_score: float,
        freshness_score: float,
        latency_ms: int,
        is_verified: bool,
    ) -> ContentVariant:
        db = self._db()
        try:
            model = ContentVariantModel(
                id=uuid4().hex,
                canonical_chapter_id=canonical_chapter_id,
                source_chapter_id=source_chapter_id,
                source_id=source_id,
                content=content,
                health_status=health_status,
                quality_score=quality_score,
                coverage_score=coverage_score,
                freshness_score=freshness_score,
                latency_ms=latency_ms,
                is_verified=is_verified,
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._variant_entity(model)
        finally:
            self._close(db)

    def list_content_variants(self, canonical_chapter_id: str) -> list[ContentVariant]:
        db = self._db()
        try:
            rows = (
                db.query(ContentVariantModel)
                .filter(ContentVariantModel.canonical_chapter_id == canonical_chapter_id)
                .order_by(ContentVariantModel.created_at.asc())
                .all()
            )
            return [self._variant_entity(row) for row in rows]
        finally:
            self._close(db)

    def get_content_variant(self, variant_id: str) -> ContentVariant | None:
        db = self._db()
        try:
            model = db.query(ContentVariantModel).filter(ContentVariantModel.id == variant_id).first()
            return self._variant_entity(model) if model else None
        finally:
            self._close(db)

    def replace_content_variant_content(self, variant_id: str, content: str) -> ContentVariant:
        db = self._db()
        try:
            model = db.query(ContentVariantModel).filter(ContentVariantModel.id == variant_id).first()
            if model is None:
                raise LookupError("content variant not found")
            model.content = content
            db.commit()
            db.refresh(model)
            return self._variant_entity(model)
        finally:
            self._close(db)

    def record_route_decision(
        self,
        *,
        tenant_id: str,
        canonical_chapter_id: str,
        selected_variant_id: str | None,
        fallback_count: int,
        route_summary: dict,
    ) -> RouteDecision:
        db = self._db()
        try:
            model = RouteDecisionModel(
                id=uuid4().hex,
                tenant_id=tenant_id,
                canonical_chapter_id=canonical_chapter_id,
                selected_variant_id=selected_variant_id,
                fallback_count=fallback_count,
                route_summary=json.dumps(route_summary, ensure_ascii=False),
            )
            db.add(model)
            db.commit()
            db.refresh(model)
            return self._route_entity(model)
        finally:
            self._close(db)

    def list_route_decisions(self, canonical_chapter_id: str) -> list[RouteDecision]:
        db = self._db()
        try:
            rows = (
                db.query(RouteDecisionModel)
                .filter(RouteDecisionModel.canonical_chapter_id == canonical_chapter_id)
                .order_by(RouteDecisionModel.created_at.asc())
                .all()
            )
            return [self._route_entity(row) for row in rows]
        finally:
            self._close(db)

    @staticmethod
    def _normalize(value: str) -> str:
        import re

        lowered = re.sub(r'\s+', ' ', (value or '').strip().lower())
        return re.sub(r'[^0-9a-z\u4e00-\u9fff ]+', '', lowered)
