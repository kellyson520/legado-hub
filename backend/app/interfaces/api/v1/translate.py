"""
翻译服务接口层 (v1 - Pro API)

职责：
- 接收 HTTP 请求
- 调用翻译应用服务
- 发布翻译领域事件
- 统一异常处理
- 全链路日志
"""

import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ....core.response import ok, fail, paginated
from ....core.logging import get_logger
from ....core.exceptions import (
    ValidationException, NotFoundException, ExternalServiceException
)
from ....core.dependencies import get_auth_context, AuthContext, require_permission
from ....core.events import publish_event, TranslationStartedEvent

from ...api.dependencies import get_translation_service
from ....application.services.translation_service import TranslationAppService

logger = get_logger("api.translate")

router = APIRouter(prefix="/api/v1/translate", tags=["translation"])


# ==================== 请求模型 ====================

class TranslateChapterRequest(BaseModel):
    """翻译章节请求"""
    book_url: str = Field(..., description="书籍 URL")
    chapter_id: str = Field(..., description="章节 ID")
    original_text: str = Field(..., description="原始文本内容")
    book_name: str = Field("", description="书籍名称")
    chapter_title: str = Field("", description="章节标题")
    provider: str = Field("llm", description="翻译提供商: llm | google")
    target_language: str = Field("", description="目标语言，默认从配置读取")


class UpdateDictionaryRequest(BaseModel):
    """更新词典请求"""
    entries: Dict[str, str] = Field(default_factory=dict, description="词典条目 {原文: 译文}")


# ==================== 翻译接口 ====================

@router.post("/chapter")
async def translate_chapter(
    req: TranslateChapterRequest,
    service: TranslationAppService = Depends(get_translation_service),
    auth: AuthContext = Depends(get_auth_context)
):
    """
    翻译章节
    
    - 支持 LLM 和 Google 两种翻译提供商
    - 自动分块、并发翻译、重试机制
    - 实时 WebSocket 进度推送
    - 结果持久化到 SQLite
    """
    if not req.book_url or not req.chapter_id or not req.original_text:
        raise ValidationException("book_url, chapter_id, original_text 不能为空")
    
    if req.provider not in ("llm", "google"):
        raise ValidationException("provider 必须是 llm 或 google")
    
    start = time.time()
    logger.info(
        f"[Translate] 翻译请求: book={req.book_name or req.book_url}, "
        f"chapter={req.chapter_title or req.chapter_id}, provider={req.provider}",
        extra={
            "action": "translate_chapter",
            "book_url": req.book_url,
            "provider": req.provider
        }
    )
    
    try:
        job = await service.translate_chapter(
            book_url=req.book_url,
            chapter_id=req.chapter_id,
            original_text=req.original_text,
            book_name=req.book_name,
            chapter_title=req.chapter_title,
            provider=req.provider,
            target_language=req.target_language
        )
        
        elapsed = (time.time() - start) * 1000
        logger.info(
            f"[Translate] 翻译完成: job_id={job.job_id}, status={job.status.value}, "
            f"elapsed={elapsed:.0f}ms",
            extra={
                "action": "translate_chapter_complete",
                "job_id": job.job_id,
                "status": job.status.value,
                "duration_ms": round(elapsed, 2)
            }
        )
        
        return ok({
            "job_id": job.job_id,
            "status": job.status.value,
            "progress": job.progress,
            "total_chunks": job.total_chunks,
            "completed_chunks": job.completed_chunks,
            "failed_chunks": job.failed_chunks,
            "translated_text": job.translated_text,
            "provider": req.provider,
            "target_language": job.target_language,
        })
        
    except ExternalServiceException:
        raise
    except Exception as e:
        logger.error(
            f"[Translate] 翻译接口异常: {type(e).__name__}: {e}",
            extra={"action": "translate_chapter_error", "error": str(e)},
            exc_info=True
        )
        raise ExternalServiceException(f"翻译失败: {e}")


@router.get("/jobs")
async def list_translation_jobs(
    book_url: Optional[str] = Query(None, description="按书籍 URL 筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: TranslationAppService = Depends(get_translation_service),
    auth: AuthContext = Depends(get_auth_context)
):
    """列出翻译任务"""
    jobs, total = await service.list_jobs(book_url, status, page, page_size)
    
    items = []
    for job in jobs:
        items.append({
            "id": job.id,
            "job_id": job.job_id,
            "book_url": job.book_url,
            "book_name": job.book_name,
            "chapter_id": job.chapter_id,
            "chapter_title": job.chapter_title,
            "status": job.status.value,
            "progress": job.progress,
            "total_chunks": job.total_chunks,
            "completed_chunks": job.completed_chunks,
            "failed_chunks": job.failed_chunks,
            "provider": job.provider.value if hasattr(job.provider, "value") else job.provider,
            "target_language": job.target_language,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        })
    
    return paginated(items, total, page, page_size)


@router.get("/jobs/{job_id}")
async def get_translation_job(
    job_id: str,
    service: TranslationAppService = Depends(get_translation_service),
    auth: AuthContext = Depends(get_auth_context)
):
    """获取翻译任务详情"""
    job = await service.get_job(job_id)
    return ok({
        "id": job.id,
        "job_id": job.job_id,
        "book_url": job.book_url,
        "book_name": job.book_name,
        "chapter_id": job.chapter_id,
        "chapter_title": job.chapter_title,
        "status": job.status.value,
        "progress": job.progress,
        "total_chunks": job.total_chunks,
        "completed_chunks": job.completed_chunks,
        "failed_chunks": job.failed_chunks,
        "error_msg": job.error_msg,
        "translated_text": job.translated_text,
        "provider": job.provider.value if hasattr(job.provider, "value") else job.provider,
        "target_language": job.target_language,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    })


@router.get("/jobs/{job_id}/result")
async def get_translation_result(
    job_id: str,
    service: TranslationAppService = Depends(get_translation_service),
    auth: AuthContext = Depends(get_auth_context)
):
    """获取翻译结果（支持部分结果实时查看）"""
    result = await service.get_translation_result(job_id)
    return ok(result)


@router.delete("/jobs/{job_id}")
async def delete_translation_job(
    job_id: str,
    service: TranslationAppService = Depends(get_translation_service),
    auth: AuthContext = Depends(require_permission("source_edit"))
):
    """删除翻译任务"""
    success = await service.delete_job(job_id)
    return ok({"deleted": success})


# ==================== 词典接口 ====================

@router.get("/dictionary/{book_url:path}")
async def get_dictionary(
    book_url: str,
    service: TranslationAppService = Depends(get_translation_service),
    auth: AuthContext = Depends(get_auth_context)
):
    """获取书籍的翻译词典"""
    dictionary = await service.get_dictionary(book_url)
    if not dictionary:
        raise NotFoundException(f"未找到词典: {book_url}")
    
    return ok({
        "book_url": dictionary.book_url,
        "book_name": dictionary.book_name,
        "entries": dictionary.entries,
        "max_entries": dictionary.max_entries,
        "total_entries": len(dictionary.entries),
        "updated_at": dictionary.updated_at.isoformat() if dictionary.updated_at else None,
    })


@router.post("/dictionary/{book_url:path}")
async def update_dictionary(
    book_url: str,
    req: UpdateDictionaryRequest,
    service: TranslationAppService = Depends(get_translation_service),
    auth: AuthContext = Depends(get_auth_context)
):
    """更新书籍的翻译词典"""
    if not req.entries:
        raise ValidationException("entries 不能为空")
    
    dictionary = await service.update_dictionary(book_url, req.entries)
    
    return ok({
        "book_url": dictionary.book_url,
        "book_name": dictionary.book_name,
        "entries": dictionary.entries,
        "total_entries": len(dictionary.entries),
    })


@router.get("/chunker/preview")
async def preview_chunks(
    text: str,
    max_chars_per_chunk: int = Query(3000, ge=500, le=8000),
    auth: AuthContext = Depends(get_auth_context)
):
    """
    预览文本分块结果（调试用）
    
    展示 ContentChunker 如何将文本拆分为多个块。
    """
    from ....services.translator import ContentChunker
    
    chunker = ContentChunker(max_chars_per_chunk=max_chars_per_chunk)
    chunks = chunker.chunk(text)
    
    return ok({
        "total_chunks": len(chunks),
        "total_chars": len(text),
        "chunks": [
            {
                "index": c.index,
                "length": c.length,
                "paragraph_indices": c.paragraph_indices,
                "preview": c.content[:200] + "..." if len(c.content) > 200 else c.content,
            }
            for c in chunks
        ]
    })
