"""
仪表盘统计接口层 (v0)

提供系统概览、书源统计、健康状态等仪表盘数据
"""

from typing import Optional
from fastapi import APIRouter, Depends

from ....core.response import ok
from ....core.logging import get_logger
from ....application.services import SourceAppService
from ..dependencies import get_source_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
logger = get_logger("api.dashboard")


@router.get("/stats")
async def get_dashboard_stats(
    svc: SourceAppService = Depends(get_source_service),
):
    """获取仪表盘统计数据"""
    # 书源统计
    book_sources, book_total = await svc.list_book_sources(page=1, page_size=1)
    rss_sources, rss_total = await svc.list_rss_sources(page=1, page_size=1)

    # 启用的书源
    enabled_book, _ = await svc.list_book_sources(enabled_only=True, page=1, page_size=1)
    enabled_rss, _ = await svc.list_rss_sources(enabled_only=True, page=1, page_size=1)

    # 状态分布
    ok_book, _ = await svc.list_book_sources(status="ok", page=1, page_size=1)
    error_book, _ = await svc.list_book_sources(status="error", page=1, page_size=1)

    # 分组统计
    groups = await svc.list_groups() if hasattr(svc, 'list_groups') else []

    return ok({
        "bookSources": {
            "total": book_total,
            "enabled": len(enabled_book),
            "disabled": book_total - len(enabled_book),
            "ok": len(ok_book),
            "error": len(error_book),
        },
        "rssSources": {
            "total": rss_total,
            "enabled": len(enabled_rss),
            "disabled": rss_total - len(enabled_rss),
        },
        "groups": groups,
        "system": {
            "version": "2.1.0",
            "engine": "Legado Engine Pro",
        },
    })


@router.get("/groups")
async def get_groups(
    svc: SourceAppService = Depends(get_source_service),
):
    """获取所有书源分组"""
    try:
        groups = await svc.list_groups()
    except Exception:
        groups = []
    return ok({"groups": groups})
