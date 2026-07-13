"""
统一输出接口层 (v0 - 兼容 API)

职责：
- 输出纯净的 Legado 兼容 JSON
- 调用应用层服务获取数据
- 不直接操作数据库
"""

from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ....core.response import ok
from ....application.services import SourceAppService
from ..dependencies import get_source_service

router = APIRouter(prefix="/api/output", tags=["output"])


@router.get("/book")
async def output_book_sources(
    group: Optional[str] = None,
    enabled_only: bool = True,
    svc: SourceAppService = Depends(get_source_service)
):
    """统一输书源（Legado 兼容格式）"""
    sources = await svc.export_book_sources(group, enabled_only)
    return ok(sources, f"共 {len(sources)} 个书源")


@router.get("/rss")
async def output_rss_sources(
    group: Optional[str] = None,
    enabled_only: bool = True,
    svc: SourceAppService = Depends(get_source_service)
):
    """统一输出订阅源（Legado 兼容格式）"""
    sources = await svc.export_rss_sources(group, enabled_only)
    return ok(sources, f"共 {len(sources)} 个订阅源")


@router.get("/all")
async def output_all_sources(
    enabled_only: bool = True,
    svc: SourceAppService = Depends(get_source_service)
):
    """统一输出所有源（Legado 兼容格式，书源+订阅源合并）"""
    result = await svc.export_all_sources(enabled_only)
    return ok(result, f"书源 {result['totalBookSources']} 个, 订阅源 {result['totalRssSources']} 个")


@router.get("/export.json")
async def export_json(
    enabled_only: bool = True,
    svc: SourceAppService = Depends(get_source_service)
):
    """导出为 Legado 订阅源 JSON 文件"""
    result = await svc.export_all_sources(enabled_only)
    all_sources = result["bookSources"] + result["rssSources"]
    
    return JSONResponse(
        content=all_sources,
        headers={"Content-Disposition": "attachment; filename=sources.json"}
    )
