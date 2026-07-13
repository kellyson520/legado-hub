"""
可用性检查接口层 (v0 - 兼容 API)
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query

from ....core.response import ok, fail
from ....application.services import SourceAppService
from ....services.fetcher import SourceChecker
from ..dependencies import get_source_service

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/check")
async def check_all_sources(
    source_type: Optional[str] = Query(None, description="book 或 rss"),
    limit: int = Query(50, ge=1, le=200),
    svc: SourceAppService = Depends(get_source_service)
):
    """批量检查源可用性"""
    checker = SourceChecker()
    results = []
    
    if source_type in (None, "book"):
        book_sources, _ = await svc.list_book_sources(enabled_only=True, page=1, page_size=limit)
        for s in book_sources:
            data = s.__dict__.copy()
            result = await checker.check_book_source(data)
            await svc._repo.update_book_source_status(s.bookSourceUrl, result["status"], result.get("errorMsg"))
            results.append({
                "sourceUrl": s.bookSourceUrl,
                "sourceName": s.bookSourceName,
                "sourceType": "book",
                **result
            })
    
    if source_type in (None, "rss"):
        rss_sources, _ = await svc.list_rss_sources(enabled_only=True, page=1, page_size=limit)
        for s in rss_sources:
            data = s.__dict__.copy()
            result = await checker.check_rss_source(data)
            await svc._repo.update_rss_source_status(s.sourceUrl, result["status"], result.get("errorMsg"))
            results.append({
                "sourceUrl": s.sourceUrl,
                "sourceName": s.sourceName,
                "sourceType": "rss",
                **result
            })
    
    ok_count = sum(1 for r in results if r["status"] == "ok")
    error_count = len(results) - ok_count
    
    return ok({
        "results": results,
        "total": len(results),
        "ok": ok_count,
        "error": error_count
    }, f"检查完成: {ok_count} 正常, {error_count} 异常")


@router.get("/check/{source_type}/{url:path}")
async def check_single_source(
    source_type: str,
    url: str,
    svc: SourceAppService = Depends(get_source_service)
):
    """检查单个源"""
    checker = SourceChecker()
    
    if source_type == "book":
        s = await svc._repo.get_book_source(url)
        if not s:
            return fail("书源不存在", "NOT_FOUND")
        data = s.__dict__.copy()
        result = await checker.check_book_source(data)
        await svc._repo.update_book_source_status(url, result["status"], result.get("errorMsg"))
    else:
        s = await svc._repo.get_rss_source(url)
        if not s:
            return fail("订阅源不存在", "NOT_FOUND")
        data = s.__dict__.copy()
        result = await checker.check_rss_source(data)
        await svc._repo.update_rss_source_status(url, result["status"], result.get("errorMsg"))
    
    return ok(result, f"状态: {result['status']}")
