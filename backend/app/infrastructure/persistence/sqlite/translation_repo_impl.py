"""
SQLite 翻译模块仓储实现

职责：
- 将领域实体转换为 SQLAlchemy ORM 对象
- 执行数据库操作
- 将 ORM 对象转换回领域实体
"""

import json
from typing import List, Optional

from ....domain.repositories.translation_repo import TranslationRepository
from ....domain.entities.translation import TranslationJob, TranslationChunk, TranslationDictionary, TranslationStatus
from ....database import (
    SessionLocal,
    TranslationJobModel, TranslationChunkModel, TranslationDictionaryModel
)
from ....core.logging import get_logger

logger = get_logger("repo.translation")


class SQLiteTranslationRepository(TranslationRepository):
    """SQLite 翻译模块仓储实现"""
    
    def _to_entity_job(self, model: TranslationJobModel) -> TranslationJob:
        """ORM -> 领域实体"""
        return TranslationJob(
            id=model.id,
            job_id=model.job_id,
            book_url=model.book_url,
            book_name=model.book_name,
            chapter_id=model.chapter_id,
            chapter_title=model.chapter_title,
            original_text=model.original_text or "",
            translated_text=model.translated_text or "",
            provider=model.provider or "llm",
            target_language=model.target_language or "zh-CN",
            status=TranslationStatus(model.status) if model.status else TranslationStatus.PENDING,
            total_chunks=model.total_chunks or 0,
            completed_chunks=model.completed_chunks or 0,
            failed_chunks=model.failed_chunks or 0,
            error_msg=model.error_msg,
            created_at=model.createdAt,
            updated_at=model.updatedAt,
        )
    
    def _to_entity_chunk(self, model: TranslationChunkModel) -> TranslationChunk:
        return TranslationChunk(
            index=model.chunk_index,
            original=model.original or "",
            translated=model.translated or "",
            status=TranslationStatus(model.status) if model.status else TranslationStatus.PENDING,
            error_msg=model.error_msg,
            created_at=model.createdAt,
            updated_at=model.updatedAt,
        )
    
    def _to_entity_dictionary(self, model: TranslationDictionaryModel) -> TranslationDictionary:
        entries = {}
        try:
            entries = json.loads(model.entries_json or "{}")
        except json.JSONDecodeError:
            logger.warning(f"[Repo] 词典 JSON 解析失败: book_url={model.book_url}")
        
        return TranslationDictionary(
            id=model.id,
            book_url=model.book_url,
            book_name=model.book_name,
            entries=entries,
            max_entries=model.max_entries or 80,
            created_at=model.createdAt,
            updated_at=model.updatedAt,
        )
    
    # ==================== TranslationJob ====================
    
    async def get_job(self, job_id: str) -> Optional[TranslationJob]:
        db = SessionLocal()
        try:
            model = db.query(TranslationJobModel).filter(TranslationJobModel.job_id == job_id).first()
            return self._to_entity_job(model) if model else None
        finally:
            db.close()
    
    async def get_job_by_id(self, id: int) -> Optional[TranslationJob]:
        db = SessionLocal()
        try:
            model = db.query(TranslationJobModel).filter(TranslationJobModel.id == id).first()
            return self._to_entity_job(model) if model else None
        finally:
            db.close()
    
    async def list_jobs(self, book_url=None, status=None, page=1, page_size=50):
        db = SessionLocal()
        try:
            query = db.query(TranslationJobModel)
            if book_url:
                query = query.filter(TranslationJobModel.book_url == book_url)
            if status:
                query = query.filter(TranslationJobModel.status == status)
            
            total = query.count()
            models = query.order_by(TranslationJobModel.createdAt.desc()).offset((page - 1) * page_size).limit(page_size).all()
            entities = [self._to_entity_job(m) for m in models]
            return entities, total
        finally:
            db.close()
    
    async def save_job(self, job: TranslationJob) -> TranslationJob:
        db = SessionLocal()
        try:
            model = db.query(TranslationJobModel).filter(TranslationJobModel.job_id == job.job_id).first()
            
            data = {
                "job_id": job.job_id,
                "book_url": job.book_url,
                "book_name": job.book_name,
                "chapter_id": job.chapter_id,
                "chapter_title": job.chapter_title,
                "original_text": job.original_text,
                "translated_text": job.translated_text,
                "provider": job.provider.value if hasattr(job.provider, "value") else str(job.provider),
                "target_language": job.target_language,
                "status": job.status.value if hasattr(job.status, "value") else str(job.status),
                "total_chunks": job.total_chunks,
                "completed_chunks": job.completed_chunks,
                "failed_chunks": job.failed_chunks,
                "error_msg": job.error_msg,
            }
            
            if model:
                for key, val in data.items():
                    if hasattr(model, key) and val is not None:
                        setattr(model, key, val)
            else:
                model = TranslationJobModel(**data)
                db.add(model)
            
            db.commit()
            db.refresh(model)
            job.id = model.id
            return job
        finally:
            db.close()
    
    async def delete_job(self, job_id: str) -> bool:
        db = SessionLocal()
        try:
            model = db.query(TranslationJobModel).filter(TranslationJobModel.job_id == job_id).first()
            if model:
                db.delete(model)
                db.commit()
                logger.info(f"[Repo] 删除翻译任务: {job_id}")
                return True
            return False
        finally:
            db.close()
    
    # ==================== TranslationChunk ====================
    
    async def get_chunk(self, job_id: str, chunk_index: int) -> Optional[TranslationChunk]:
        db = SessionLocal()
        try:
            model = db.query(TranslationChunkModel).filter(
                TranslationChunkModel.job_id == job_id,
                TranslationChunkModel.chunk_index == chunk_index
            ).first()
            return self._to_entity_chunk(model) if model else None
        finally:
            db.close()
    
    async def list_chunks(self, job_id: str) -> List[TranslationChunk]:
        db = SessionLocal()
        try:
            models = db.query(TranslationChunkModel).filter(
                TranslationChunkModel.job_id == job_id
            ).order_by(TranslationChunkModel.chunk_index).all()
            return [self._to_entity_chunk(m) for m in models]
        finally:
            db.close()
    
    async def save_chunk(self, job_id: str, chunk: TranslationChunk) -> TranslationChunk:
        db = SessionLocal()
        try:
            model = db.query(TranslationChunkModel).filter(
                TranslationChunkModel.job_id == job_id,
                TranslationChunkModel.chunk_index == chunk.index
            ).first()
            
            data = {
                "job_id": job_id,
                "chunk_index": chunk.index,
                "original": chunk.original,
                "translated": chunk.translated,
                "status": chunk.status.value if hasattr(chunk.status, "value") else str(chunk.status),
                "error_msg": chunk.error_msg,
            }
            
            if model:
                for key, val in data.items():
                    if hasattr(model, key) and val is not None:
                        setattr(model, key, val)
            else:
                model = TranslationChunkModel(**data)
                db.add(model)
            
            db.commit()
            return chunk
        finally:
            db.close()
    
    async def save_chunks(self, job_id: str, chunks: List[TranslationChunk]) -> int:
        db = SessionLocal()
        count = 0
        try:
            for chunk in chunks:
                model = db.query(TranslationChunkModel).filter(
                    TranslationChunkModel.job_id == job_id,
                    TranslationChunkModel.chunk_index == chunk.index
                ).first()
                
                data = {
                    "job_id": job_id,
                    "chunk_index": chunk.index,
                    "original": chunk.original,
                    "translated": chunk.translated,
                    "status": chunk.status.value if hasattr(chunk.status, "value") else str(chunk.status),
                    "error_msg": chunk.error_msg,
                }
                
                if model:
                    for key, val in data.items():
                        if hasattr(model, key) and val is not None:
                            setattr(model, key, val)
                else:
                    model = TranslationChunkModel(**data)
                    db.add(model)
                count += 1
            
            db.commit()
            return count
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    async def delete_chunks(self, job_id: str) -> bool:
        db = SessionLocal()
        try:
            db.query(TranslationChunkModel).filter(TranslationChunkModel.job_id == job_id).delete()
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    # ==================== TranslationDictionary ====================
    
    async def get_dictionary(self, book_url: str) -> Optional[TranslationDictionary]:
        db = SessionLocal()
        try:
            model = db.query(TranslationDictionaryModel).filter(
                TranslationDictionaryModel.book_url == book_url
            ).first()
            return self._to_entity_dictionary(model) if model else None
        finally:
            db.close()
    
    async def save_dictionary(self, dictionary: TranslationDictionary) -> TranslationDictionary:
        db = SessionLocal()
        try:
            model = db.query(TranslationDictionaryModel).filter(
                TranslationDictionaryModel.book_url == dictionary.book_url
            ).first()
            
            data = {
                "book_url": dictionary.book_url,
                "book_name": dictionary.book_name,
                "entries_json": json.dumps(dictionary.entries, ensure_ascii=False),
                "max_entries": dictionary.max_entries,
            }
            
            if model:
                for key, val in data.items():
                    if hasattr(model, key) and val is not None:
                        setattr(model, key, val)
            else:
                model = TranslationDictionaryModel(**data)
                db.add(model)
            
            db.commit()
            db.refresh(model)
            dictionary.id = model.id
            return dictionary
        finally:
            db.close()
    
    async def delete_dictionary(self, book_url: str) -> bool:
        db = SessionLocal()
        try:
            model = db.query(TranslationDictionaryModel).filter(
                TranslationDictionaryModel.book_url == book_url
            ).first()
            if model:
                db.delete(model)
                db.commit()
                return True
            return False
        finally:
            db.close()
