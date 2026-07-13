import asyncio
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db, BookSourceModel, RssSourceModel
from ..models import ApiResponse, PaginatedResponse
from ..services.fetcher import SourceChecker

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/check", response_model=ApiResponse)
async def check_all_sources(
    source_type: Optional[str] = Query(None, description="book 或 rss"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """批量检查源可用性"""
    checker = SourceChecker()
    results = []
    
    if source_type in (None, "book"):
        book_sources = db.query(BookSourceModel).filter(BookSourceModel.enabled == True).limit(limit).all()
        for s in book_sources:
            data = {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
            result = await checker.check_book_source(data)
            s.sourceStatus = result["status"]
            s.lastCheckTime = datetime.utcnow()
            s.errorMsg = result.get("errorMsg")
            results.append({
                "sourceUrl": s.bookSourceUrl,
                "sourceName": s.bookSourceName,
                "sourceType": "book",
                **result
            })
    
    if source_type in (None, "rss"):
        rss_sources = db.query(RssSourceModel).filter(RssSourceModel.enabled == True).limit(limit).all()
        for s in rss_sources:
            data = {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
            result = await checker.check_rss_source(data)
            s.sourceStatus = result["status"]
            s.lastCheckTime = datetime.utcnow()
            s.errorMsg = result.get("errorMsg")
            results.append({
                "sourceUrl": s.sourceUrl,
                "sourceName": s.sourceName,
                "sourceType": "rss",
                **result
            })
    
    db.commit()
    
    ok_count = sum(1 for r in results if r["status"] == "ok")
    error_count = len(results) - ok_count
    
    return ApiResponse(
        data={
            "results": results,
            "total": len(results),
            "ok": ok_count,
            "error": error_count
        },
        message=f"检查完成: {ok_count} 正常, {error_count} 异常"
    )


@router.get("/check/{source_type}/{url:path}", response_model=ApiResponse)
async def check_single_source(source_type: str, url: str, db: Session = Depends(get_db)):
    """检查单个源"""
    checker = SourceChecker()
    
    if source_type == "book":
        s = db.query(BookSourceModel).filter(BookSourceModel.bookSourceUrl == url).first()
        if not s:
            return ApiResponse(success=False, message="书源不存在")
        data = {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
        result = await checker.check_book_source(data)
        s.sourceStatus = result["status"]
        s.lastCheckTime = datetime.utcnow()
        s.errorMsg = result.get("errorMsg")
    else:
        s = db.query(RssSourceModel).filter(RssSourceModel.sourceUrl == url).first()
        if not s:
            return ApiResponse(success=False, message="订阅源不存在")
        data = {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
        result = await checker.check_rss_source(data)
        s.sourceStatus = result["status"]
        s.lastCheckTime = datetime.utcnow()
        s.errorMsg = result.get("errorMsg")
    
    db.commit()
    return ApiResponse(data=result, message=f"状态: {result['status']}")
