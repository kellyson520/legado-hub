from datetime import datetime

from app.domain.repositories.quota_repo import QuotaUsageRepository
from app.infrastructure.persistence.sqlite.session import SessionLocal

from .schema import QuotaUsageModel


class SQLiteQuotaUsageRepository(QuotaUsageRepository):
    async def upsert_max_usage(
        self,
        *,
        api_key_id: int,
        date: str,
        fetch_count: int,
        ai_chars: int,
        storage_mb: float,
    ) -> None:
        db = SessionLocal()
        try:
            usage = (
                db.query(QuotaUsageModel)
                .filter(
                    QuotaUsageModel.api_key_id == api_key_id,
                    QuotaUsageModel.date == date,
                )
                .first()
            )
            if usage is None:
                usage = QuotaUsageModel(
                    api_key_id=api_key_id,
                    date=date,
                    fetch_count=fetch_count,
                    ai_chars=ai_chars,
                    storage_mb=storage_mb,
                )
                db.add(usage)
            else:
                usage.fetch_count = max(usage.fetch_count or 0, fetch_count)
                usage.ai_chars = max(usage.ai_chars or 0, ai_chars)
                usage.storage_mb = max(usage.storage_mb or 0.0, storage_mb)
                usage.updated_at = datetime.utcnow()
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
