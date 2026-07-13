"""
Novel Understanding API (v1)

小说理解系统 API 端点：
- 书籍管理（摄入、查询、删除）
- 章节管理
- 实体与知识图谱
- RAG 检索与问答
- 分析 prompt 生成
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends

from ....core.response import ok, paginated, fail
from ....core.logging import get_logger
from ....core.exceptions import NotFoundException, ValidationException

logger = get_logger("api.v1.novel")

router = APIRouter(prefix="/api/v1/novels", tags=["novel"])


# ==================== 依赖注入 ====================

_novel_service_singleton = None
_novel_db = None

async def get_novel_service():
    """获取 NovelAppService 实例（延迟导入+单例）"""
    global _novel_service_singleton, _novel_db
    if _novel_service_singleton is not None:
        return _novel_service_singleton
    
    from app.application.services.novel_app_service import NovelAppService
    from app.infrastructure.persistence.sqlite.novel_repo_impl import SqliteNovelRepository
    import aiosqlite
    import os
    from app.core.config import settings

    db_path = getattr(settings, "NOVEL_DB_PATH", "data/novel.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _novel_db = await aiosqlite.connect(db_path)
    await _novel_db.execute("PRAGMA journal_mode=WAL")
    await _novel_db.execute("PRAGMA foreign_keys=ON")
    import os as _os
    base_dir = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    schema_path = _os.path.join(base_dir, "database_migrations", "novel_schema.sql")
    if _os.path.exists(schema_path):
        with open(schema_path) as f:
            await _novel_db.executescript(f.read())
        await _novel_db.commit()
    
    repo = SqliteNovelRepository(_novel_db)
    _novel_service_singleton = NovelAppService(repo)
    return _novel_service_singleton


# ==================== 书籍管理 ====================

@router.post("/ingest")
async def ingest_book_catalog(
    book_url: str,
    book_name: str,
    raw_titles: List[str],
    author: str = "",
    source_name: str = "",
):
    """
    摄入小说目录

    - 解析章节标题，生成标准化编号
    - 批量保存章节元数据
    - 返回书籍基本信息
    """
    try:
        service = await get_novel_service()
        book = await service.ingest_book_catalog(
            book_url=book_url,
            book_name=book_name,
            raw_titles=raw_titles,
            author=author,
            source_name=source_name,
        )
        return ok({
            "book_id": book.id,
            "book_name": book.book_name,
            "total_chapters": book.total_chapters,
            "status": book.status.value,
        }, message="目录摄入成功")
    except Exception as e:
        logger.error(f"[novel.ingest] 摄入失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _safe_isoformat(dt):
    """安全转换 datetime 为 ISO 字符串，已为字符串则直接返回"""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


@router.get("")
async def list_books(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取书籍列表"""
    try:
        service = await get_novel_service()
        result = await service.list_books(page=page, page_size=page_size)
        return paginated(
            items=[
                {
                    "id": b.id,
                    "book_name": b.book_name,
                    "book_url": b.book_url,
                    "author": b.author,
                    "total_chapters": b.total_chapters,
                    "status": b.status.value,
                    "ingest_progress": b.ingest_progress,
                    "updated_at": _safe_isoformat(b.updated_at),
                }
                for b in result["items"]
            ],
            total=result["total"],
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"[novel.list] 查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{book_id}")
async def get_book_detail(book_id: int):
    """获取书籍详情"""
    try:
        service = await get_novel_service()
        book = await service.get_book(book_id)
        if not book:
            raise NotFoundException(f"书籍不存在: {book_id}")
        return ok({
            "id": book.id,
            "book_name": book.book_name,
            "book_url": book.book_url,
            "author": book.author,
            "source_name": book.source_name,
            "total_chapters": book.total_chapters,
            "total_words": book.total_words,
            "status": book.status.value,
            "ingest_progress": book.ingest_progress,
            "summary_global": book.summary_global,
            "entity_count": book.entity_count,
            "relationship_count": book.relationship_count,
            "event_count": book.event_count,
            "created_at": _safe_isoformat(book.created_at),
            "updated_at": _safe_isoformat(book.updated_at),
        })
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"[novel.detail] 查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{book_id}")
async def delete_book(book_id: int):
    """删除书籍及其所有相关数据"""
    try:
        service = await get_novel_service()
        result = await service.delete_book(book_id)
        if not result:
            raise NotFoundException(f"书籍不存在: {book_id}")
        return ok(message="删除成功")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"[novel.delete] 删除失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 章节管理 ====================

@router.get("/{book_id}/chapters")
async def list_chapters(
    book_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
):
    """获取书籍章节列表"""
    try:
        service = await get_novel_service()
        result = await service.get_chapters(book_id, page=page, page_size=page_size)
        return paginated(
            items=[
                {
                    "id": c.id,
                    "canonical_full": c.canonical_full,
                    "canonical_num": c.canonical_num,
                    "chapter_title": c.chapter_title,
                    "raw_title": c.raw_title,
                    "word_count": c.word_count,
                    "quality_score": c.quality_score,
                    "summary": c.summary,
                }
                for c in result["items"]
            ],
            total=result["total"],
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"[novel.chapters] 查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chapters/{chapter_id}")
async def get_chapter_detail(chapter_id: int):
    """获取章节详情"""
    try:
        service = await get_novel_service()
        chapter = await service.get_chapter(chapter_id)
        if not chapter:
            raise NotFoundException(f"章节不存在: {chapter_id}")
        return ok({
            "id": chapter.id,
            "book_id": chapter.book_id,
            "canonical_full": chapter.canonical_full,
            "canonical_type": chapter.canonical_type,
            "canonical_num": chapter.canonical_num,
            "chapter_title": chapter.chapter_title,
            "raw_title": chapter.raw_title,
            "word_count": chapter.word_count,
            "quality_score": chapter.quality_score,
            "summary": chapter.summary,
            "key_events": chapter.key_events,
            "mood_tags": chapter.mood_tags,
            "arc_tag": chapter.arc_tag,
            "arc_summary": chapter.arc_summary,
            "raw_text": chapter.raw_text,
        })
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"[novel.chapter] 查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/chapters/{chapter_id}/content")
async def save_chapter_content(
    chapter_id: int,
    content: str,
    quality_score: Optional[float] = None,
):
    """保存章节内容（带质量评分）"""
    try:
        service = await get_novel_service()
        result = await service.save_chapter_content(
            chapter_id=chapter_id,
            content=content,
            quality_score=quality_score,
        )
        if not result:
            raise NotFoundException(f"章节不存在: {chapter_id}")
        return ok(message="章节内容保存成功")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"[novel.chapter.content] 保存失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 实体与知识图谱 ====================

@router.get("/{book_id}/entities")
async def list_entities(
    book_id: int,
    entity_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """获取书籍实体列表"""
    try:
        service = await get_novel_service()
        result = await service.get_entities(
            book_id, entity_type=entity_type, page=page, page_size=page_size
        )
        return paginated(
            items=[
                {
                    "id": e.id,
                    "name": e.name,
                    "entity_type": e.entity_type.value,
                    "description": e.description,
                    "aliases": e.aliases,
                    "importance_score": e.importance_score,
                    "first_appearance_ch": e.first_appearance_ch,
                    "appearance_count": e.appearance_count,
                }
                for e in result["items"]
            ],
            total=result["total"],
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"[novel.entities] 查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{book_id}/entities/{entity_name}/relations")
async def get_entity_relations(book_id: int, entity_name: str):
    """获取实体关系网络"""
    try:
        service = await get_novel_service()
        result = await service.get_character_relations(book_id, entity_name)
        return ok({
            "entity": {
                "name": result["entity"].name,
                "entity_type": result["entity"].entity_type.value,
                "description": result["entity"].description,
            } if result["entity"] else None,
            "relationships": [
                {
                    "id": r.id,
                    "source": r.source_entity,
                    "target": r.target_entity,
                    "relation_type": r.relation_type.value,
                    "description": r.description,
                    "since_chapter": r.since_chapter,
                    "confidence": r.confidence,
                }
                for r in result["relationships"]
            ],
        })
    except Exception as e:
        logger.error(f"[novel.relations] 查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 分析 Prompt 生成 ====================

@router.post("/{book_id}/analysis/character")
async def build_character_analysis(
    book_id: int,
    character_name: str,
):
    """构建人物分析 Prompt（返回 prompt，实际 LLM 调用由调用方负责）"""
    try:
        service = await get_novel_service()
        result = await service.build_character_analysis_prompt(book_id, character_name)
        return ok({
            "system_prompt": result["system"],
            "user_prompt": result["user"],
            "character_name": character_name,
        }, message="人物分析 prompt 生成成功")
    except ValueError as e:
        raise NotFoundException(str(e))
    except Exception as e:
        logger.error(f"[novel.analysis.character] 生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{book_id}/analysis/world")
async def build_world_analysis(book_id: int):
    """构建世界观分析 Prompt"""
    try:
        service = await get_novel_service()
        result = await service.build_world_analysis_prompt(book_id)
        return ok({
            "system_prompt": result["system"],
            "user_prompt": result["user"],
        }, message="世界观分析 prompt 生成成功")
    except ValueError as e:
        raise NotFoundException(str(e))
    except Exception as e:
        logger.error(f"[novel.analysis.world] 生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{book_id}/analysis/storyline")
async def build_storyline_analysis(book_id: int):
    """构建剧情时间线 Prompt"""
    try:
        service = await get_novel_service()
        result = await service.build_storyline_prompt(book_id)
        return ok({
            "system_prompt": result["system"],
            "user_prompt": result["user"],
        }, message="剧情线 prompt 生成成功")
    except ValueError as e:
        raise NotFoundException(str(e))
    except Exception as e:
        logger.error(f"[novel.analysis.storyline] 生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== RAG 问答 ====================

@router.post("/{book_id}/chat")
async def novel_chat(
    book_id: int,
    question: str,
):
    """
    小说问答（RAG 检索增强生成）

    返回带检索上下文的 prompt，实际 LLM 调用由调用方负责。
    同时返回检索到的相关章节片段。
    """
    try:
        if not question or not question.strip():
            raise ValidationException("问题不能为空")

        service = await get_novel_service()
        result = await service.build_chat_prompt(book_id, question.strip())
        return ok({
            "system_prompt": result["system"],
            "user_prompt": result["user"],
            "question": question,
            "retrieval_results": result["retrieval_results"],
        }, message="检索完成，prompt 已生成")
    except ValidationException:
        raise
    except ValueError as e:
        raise NotFoundException(str(e))
    except Exception as e:
        logger.error(f"[novel.chat] 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 自动提取（独立运行） ====================

@router.post("/{book_id}/auto-extract")
async def auto_extract_entities(book_id: int):
    """
    自动提取全书实体和关系（系统独立运行，不依赖外部 LLM）
    
    扫描所有已保存的章节内容，使用本地规则提取器：
    - 自动识别人物、地点、势力等实体
    - 推断人物关系（师徒、盟友、敌对等）
    - 计算实体重要度和出现频率
    """
    try:
        service = await get_novel_service()
        result = await service.auto_extract_entities(book_id)
        return ok(result, message=result.get("message", "自动提取完成"))
    except ValueError as e:
        raise NotFoundException(str(e))
    except Exception as e:
        logger.error(f"[novel.auto_extract] 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
