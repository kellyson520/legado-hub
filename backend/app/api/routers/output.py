import json
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db, BookSourceModel, RssSourceModel, FilterRuleModel
from ..models import ApiResponse

router = APIRouter(prefix="/api/output", tags=["output"])


def _clean_hub_fields(d: dict) -> dict:
    """移除 hub 内部字段，输出纯净的 Legado 格式"""
    hub_fields = {"sourceStatus", "lastCheckTime", "errorMsg", "sourceOrigin", "createdAt", "updatedAt", "id"}
    return {k: v for k, v in d.items() if k not in hub_fields and v is not None and v != ""}


@router.get("/book", response_model=ApiResponse)
async def output_book_sources(
    group: Optional[str] = None,
    enabled_only: bool = True,
    db: Session = Depends(get_db)
):
    """统一输书源（Legado 兼容格式）"""
    query = db.query(BookSourceModel)
    if enabled_only:
        query = query.filter(BookSourceModel.enabled == True)
    if group:
        query = query.filter(BookSourceModel.bookSourceGroup.contains(group))
    
    items = query.all()
    sources = []
    for item in items:
        d = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
        sources.append(_clean_hub_fields(d))
    
    return ApiResponse(data=sources, message=f"共 {len(sources)} 个书源")


@router.get("/rss", response_model=ApiResponse)
async def output_rss_sources(
    group: Optional[str] = None,
    enabled_only: bool = True,
    db: Session = Depends(get_db)
):
    """统一输出订阅源（Legado 兼容格式）"""
    query = db.query(RssSourceModel)
    if enabled_only:
        query = query.filter(RssSourceModel.enabled == True)
    if group:
        query = query.filter(RssSourceModel.sourceGroup.contains(group))
    
    items = query.all()
    sources = []
    for item in items:
        d = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
        sources.append(_clean_hub_fields(d))
    
    return ApiResponse(data=sources, message=f"共 {len(sources)} 个订阅源")


@router.get("/all", response_model=ApiResponse)
async def output_all_sources(
    enabled_only: bool = True,
    db: Session = Depends(get_db)
):
    """统一输出所有源（Legado 兼容格式，书源+订阅源合并）"""
    book_query = db.query(BookSourceModel)
    rss_query = db.query(RssSourceModel)
    
    if enabled_only:
        book_query = book_query.filter(BookSourceModel.enabled == True)
        rss_query = rss_query.filter(RssSourceModel.enabled == True)
    
    book_items = book_query.all()
    rss_items = rss_query.all()
    
    book_sources = []
    for item in book_items:
        d = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
        book_sources.append(_clean_hub_fields(d))
    
    rss_sources = []
    for item in rss_items:
        d = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
        rss_sources.append(_clean_hub_fields(d))
    
    return ApiResponse(data={
        "bookSources": book_sources,
        "rssSources": rss_sources,
        "totalBookSources": len(book_sources),
        "totalRssSources": len(rss_sources)
    }, message=f"书源 {len(book_sources)} 个, 订阅源 {len(rss_sources)} 个")


@router.get("/export.json")
async def export_json(
    enabled_only: bool = True,
    db: Session = Depends(get_db)
):
    """导出为 Legado 订阅源 JSON 文件"""
    book_query = db.query(BookSourceModel)
    rss_query = db.query(RssSourceModel)
    
    if enabled_only:
        book_query = book_query.filter(BookSourceModel.enabled == True)
        rss_query = rss_query.filter(RssSourceModel.enabled == True)
    
    all_sources = []
    for item in book_query.all():
        d = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
        all_sources.append(_clean_hub_fields(d))
    for item in rss_query.all():
        d = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
        all_sources.append(_clean_hub_fields(d))
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=all_sources,
        headers={"Content-Disposition": "attachment; filename=sources.json"}
    )
