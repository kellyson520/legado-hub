import json
from datetime import datetime

from sqlalchemy import func

from app.database import SessionLocal
from app.domain.repositories.source_repo import SourceRepository

from .schema import BookSourceModel, FilterRuleModel, RssSourceModel, SubscriptionModel


class SQLiteSourceRepository(SourceRepository):
    @staticmethod
    def _safe_json_loads(raw: str | None) -> dict:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _book_to_dict(self, model: BookSourceModel) -> dict:
        payload = self._safe_json_loads(model.payload)
        merged = {
            "id": model.id,
            "bookSourceName": model.bookSourceName,
            "bookSourceUrl": model.bookSourceUrl,
            "bookSourceGroup": model.bookSourceGroup,
            "enabled": model.enabled,
            "sourceStatus": model.sourceStatus,
            "sourceOrigin": model.sourceOrigin,
            "lastCheckTime": model.lastCheckTime.isoformat() if model.lastCheckTime else None,
            "errorMsg": model.errorMsg,
        }
        merged.update(payload)
        merged["id"] = model.id
        merged["bookSourceName"] = model.bookSourceName
        merged["bookSourceUrl"] = model.bookSourceUrl
        merged["bookSourceGroup"] = model.bookSourceGroup
        merged["enabled"] = model.enabled
        merged["sourceStatus"] = model.sourceStatus
        merged["sourceOrigin"] = model.sourceOrigin
        merged["lastCheckTime"] = model.lastCheckTime.isoformat() if model.lastCheckTime else None
        merged["errorMsg"] = model.errorMsg
        return merged

    @staticmethod
    def _extract_book_source_columns(data: dict) -> dict:
        return {
            "bookSourceName": data.get("bookSourceName", ""),
            "bookSourceUrl": data.get("bookSourceUrl", ""),
            "bookSourceGroup": data.get("bookSourceGroup") or "default",
            "enabled": bool(data.get("enabled", True)),
            "payload": json.dumps(data, ensure_ascii=False),
            "sourceStatus": data.get("sourceStatus", "unknown"),
            "sourceOrigin": data.get("sourceOrigin"),
            "errorMsg": data.get("errorMsg"),
        }

    async def list_book_sources(
        self, page: int, page_size: int, enabled_only: bool = False
    ) -> tuple[list[dict], int]:
        db = SessionLocal()
        try:
            query = db.query(BookSourceModel).order_by(BookSourceModel.id.asc())
            if enabled_only:
                query = query.filter(BookSourceModel.enabled == True)
            total = query.count()
            rows = query.offset((page - 1) * page_size).limit(page_size).all()
            return [self._book_to_dict(row) for row in rows], total
        finally:
            db.close()

    async def create_book_source(self, data: dict, actor_id: int) -> dict:
        db = SessionLocal()
        try:
            model = BookSourceModel(**self._extract_book_source_columns(data))
            db.add(model)
            db.commit()
            db.refresh(model)
            payload = self._book_to_dict(model)
            payload["created_by"] = actor_id
            return payload
        finally:
            db.close()

    async def update_book_source(self, source_id: int, data: dict, actor_id: int) -> dict:
        db = SessionLocal()
        try:
            model = db.query(BookSourceModel).filter(BookSourceModel.id == source_id).first()
            merged_payload = self._safe_json_loads(model.payload)
            merged_payload.update(data)
            columns = self._extract_book_source_columns(merged_payload)
            for key, value in columns.items():
                setattr(model, key, value)
            db.commit()
            db.refresh(model)
            payload = self._book_to_dict(model)
            payload["updated_by"] = actor_id
            return payload
        finally:
            db.close()

    async def delete_book_source(self, source_id: int, actor_id: int) -> None:
        db = SessionLocal()
        try:
            db.query(BookSourceModel).filter(BookSourceModel.id == source_id).delete()
            db.commit()
        finally:
            db.close()

    async def list_groups(self) -> list[dict]:
        db = SessionLocal()
        try:
            rows = (
                db.query(BookSourceModel.bookSourceGroup, func.count(BookSourceModel.id))
                .group_by(BookSourceModel.bookSourceGroup)
                .order_by(BookSourceModel.bookSourceGroup.asc())
                .all()
            )
            return [{"name": row[0] or "default", "count": row[1]} for row in rows]
        finally:
            db.close()

    async def export_book_sources(self, enabled_only: bool = False) -> list[dict]:
        items, _ = await self.list_book_sources(page=1, page_size=10000, enabled_only=enabled_only)
        return items

    async def upsert_book_sources(self, items: list[dict], actor_id: int) -> int:
        db = SessionLocal()
        try:
            count = 0
            for item in items:
                url = item.get("bookSourceUrl")
                if not url:
                    continue
                columns = self._extract_book_source_columns(item)
                model = db.query(BookSourceModel).filter(BookSourceModel.bookSourceUrl == url).first()
                if model is None:
                    db.add(BookSourceModel(**columns))
                else:
                    for key, value in columns.items():
                        setattr(model, key, value)
                count += 1
            db.commit()
            return count
        finally:
            db.close()

    async def list_book_sources_full(
        self,
        enabled_only: bool = False,
        ids: list[int] | None = None,
        urls: list[str] | None = None,
    ) -> list[dict]:
        db = SessionLocal()
        try:
            query = db.query(BookSourceModel).order_by(BookSourceModel.id.asc())
            if enabled_only:
                query = query.filter(BookSourceModel.enabled == True)
            if ids:
                query = query.filter(BookSourceModel.id.in_(ids))
            if urls:
                query = query.filter(BookSourceModel.bookSourceUrl.in_(urls))
            return [self._book_to_dict(row) for row in query.all()]
        finally:
            db.close()

    async def health_snapshot(self) -> dict:
        db = SessionLocal()
        try:
            return {
                "book_sources_total": db.query(BookSourceModel).count(),
                "book_sources_enabled": db.query(BookSourceModel).filter(BookSourceModel.enabled == True).count(),
                "rss_sources_total": db.query(RssSourceModel).count(),
                "subscriptions_total": db.query(SubscriptionModel).count(),
                "filter_rules_total": db.query(FilterRuleModel).count(),
            }
        finally:
            db.close()

    async def update_book_source_health_fields(
        self,
        source_id: int,
        source_status: str,
        error_msg: str,
        last_check_time: datetime,
    ) -> dict:
        db = SessionLocal()
        try:
            model = db.query(BookSourceModel).filter(BookSourceModel.id == source_id).first()
            if model is None:
                raise ValueError(f"book source not found: {source_id}")
            model.sourceStatus = source_status
            model.errorMsg = error_msg
            model.lastCheckTime = last_check_time
            db.commit()
            db.refresh(model)
            return self._book_to_dict(model)
        finally:
            db.close()
