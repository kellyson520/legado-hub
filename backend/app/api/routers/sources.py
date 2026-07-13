import json
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db, BookSourceModel, RssSourceModel, SubscriptionModel, SourceLogModel, FilterRuleModel
from ..models import (
    BookSource, RssSource, Subscription, SubscriptionCreate,
    FilterRule, FilterRuleCreate, ApiResponse, PaginatedResponse
)
from ..services.fetcher import SourceFetcher

router = APIRouter(prefix="/api/sources", tags=["sources"])

# ==================== BookSource APIs ====================

@router.get("/book", response_model=PaginatedResponse)
async def list_book_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: Optional[str] = None,
    group: Optional[str] = None,
    status: Optional[str] = None,
    enabled_only: bool = False,
    db: Session = Depends(get_db)
):
    query = db.query(BookSourceModel)
    
    if search:
        query = query.filter(
            BookSourceModel.bookSourceName.contains(search) |
            BookSourceModel.bookSourceUrl.contains(search) |
            BookSourceModel.bookSourceComment.contains(search)
        )
    if group:
        query = query.filter(BookSourceModel.bookSourceGroup.contains(group))
    if status:
        query = query.filter(BookSourceModel.sourceStatus == status)
    if enabled_only:
        query = query.filter(BookSourceModel.enabled == True)
    
    total = query.count()
    items = query.order_by(BookSourceModel.weight.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        data=[{k: v for k, v in item.__dict__.items() if not k.startswith("_")} for item in items],
        total=total,
        page=page,
        pageSize=page_size
    )

@router.get("/book/{url:path}", response_model=ApiResponse)
async def get_book_source(url: str, db: Session = Depends(get_db)):
    item = db.query(BookSourceModel).filter(BookSourceModel.bookSourceUrl == url).first()
    if not item:
        raise HTTPException(status_code=404, detail="书源不存在")
    return ApiResponse(data={k: v for k, v in item.__dict__.items() if not k.startswith("_")})

@router.post("/book", response_model=ApiResponse)
async def create_or_update_book_source(source: BookSource, db: Session = Depends(get_db)):
    existing = db.query(BookSourceModel).filter(BookSourceModel.bookSourceUrl == source.bookSourceUrl).first()
    data = source.dict(exclude_unset=True)
    
    if existing:
        for k, v in data.items():
            if hasattr(existing, k) and v is not None:
                setattr(existing, k, v)
    else:
        db.add(BookSourceModel(**data))
    
    db.commit()
    return ApiResponse(message="保存成功")

@router.delete("/book/{url:path}", response_model=ApiResponse)
async def delete_book_source(url: str, db: Session = Depends(get_db)):
    item = db.query(BookSourceModel).filter(BookSourceModel.bookSourceUrl == url).first()
    if not item:
        raise HTTPException(status_code=404, detail="书源不存在")
    db.delete(item)
    db.commit()
    return ApiResponse(message="删除成功")

@router.post("/book/import", response_model=ApiResponse)
async def import_book_sources(sources: List[dict], db: Session = Depends(get_db)):
    count = 0
    for s in sources:
        url = s.get("bookSourceUrl")
        if not url:
            continue
        existing = db.query(BookSourceModel).filter(BookSourceModel.bookSourceUrl == url).first()
        if existing:
            for k, v in s.items():
                if hasattr(existing, k) and v is not None:
                    setattr(existing, k, v)
        else:
            db.add(BookSourceModel(**{k: v for k, v in s.items() if hasattr(BookSourceModel, k)}))
        count += 1
    db.commit()
    return ApiResponse(message=f"导入 {count} 个书源成功")

# ==================== RssSource APIs ====================

@router.get("/rss", response_model=PaginatedResponse)
async def list_rss_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: Optional[str] = None,
    group: Optional[str] = None,
    status: Optional[str] = None,
    enabled_only: bool = False,
    db: Session = Depends(get_db)
):
    query = db.query(RssSourceModel)
    
    if search:
        query = query.filter(
            RssSourceModel.sourceName.contains(search) |
            RssSourceModel.sourceUrl.contains(search) |
            RssSourceModel.sourceComment.contains(search)
        )
    if group:
        query = query.filter(RssSourceModel.sourceGroup.contains(group))
    if status:
        query = query.filter(RssSourceModel.sourceStatus == status)
    if enabled_only:
        query = query.filter(RssSourceModel.enabled == True)
    
    total = query.count()
    items = query.order_by(RssSourceModel.customOrder).offset((page - 1) * page_size).limit(page_size).all()
    
    return PaginatedResponse(
        data=[{k: v for k, v in item.__dict__.items() if not k.startswith("_")} for item in items],
        total=total,
        page=page,
        pageSize=page_size
    )

@router.get("/rss/{url:path}", response_model=ApiResponse)
async def get_rss_source(url: str, db: Session = Depends(get_db)):
    item = db.query(RssSourceModel).filter(RssSourceModel.sourceUrl == url).first()
    if not item:
        raise HTTPException(status_code=404, detail="订阅源不存在")
    return ApiResponse(data={k: v for k, v in item.__dict__.items() if not k.startswith("_")})

@router.post("/rss", response_model=ApiResponse)
async def create_or_update_rss_source(source: RssSource, db: Session = Depends(get_db)):
    existing = db.query(RssSourceModel).filter(RssSourceModel.sourceUrl == source.sourceUrl).first()
    data = source.dict(exclude_unset=True)
    
    if existing:
        for k, v in data.items():
            if hasattr(existing, k) and v is not None:
                setattr(existing, k, v)
    else:
        db.add(RssSourceModel(**data))
    
    db.commit()
    return ApiResponse(message="保存成功")

@router.delete("/rss/{url:path}", response_model=ApiResponse)
async def delete_rss_source(url: str, db: Session = Depends(get_db)):
    item = db.query(RssSourceModel).filter(RssSourceModel.sourceUrl == url).first()
    if not item:
        raise HTTPException(status_code=404, detail="订阅源不存在")
    db.delete(item)
    db.commit()
    return ApiResponse(message="删除成功")

@router.post("/rss/import", response_model=ApiResponse)
async def import_rss_sources(sources: List[dict], db: Session = Depends(get_db)):
    count = 0
    for s in sources:
        url = s.get("sourceUrl")
        if not url:
            continue
        existing = db.query(RssSourceModel).filter(RssSourceModel.sourceUrl == url).first()
        if existing:
            for k, v in s.items():
                if hasattr(existing, k) and v is not None:
                    setattr(existing, k, v)
        else:
            db.add(RssSourceModel(**{k: v for k, v in s.items() if hasattr(RssSourceModel, k)}))
        count += 1
    db.commit()
    return ApiResponse(message=f"导入 {count} 个订阅源成功")

# ==================== Subscription APIs ====================

@router.get("/subscription", response_model=PaginatedResponse)
async def list_subscriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    total = db.query(SubscriptionModel).count()
    items = db.query(SubscriptionModel).order_by(SubscriptionModel.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        data=[{k: v for k, v in item.__dict__.items() if not k.startswith("_")} for item in items],
        total=total,
        page=page,
        pageSize=page_size
    )

@router.post("/subscription", response_model=ApiResponse)
async def create_subscription(sub: SubscriptionCreate, db: Session = Depends(get_db)):
    item = SubscriptionModel(**sub.dict())
    db.add(item)
    db.commit()
    db.refresh(item)
    return ApiResponse(data={"id": item.id}, message="创建成功")

@router.delete("/subscription/{sub_id}", response_model=ApiResponse)
async def delete_subscription(sub_id: int, db: Session = Depends(get_db)):
    item = db.query(SubscriptionModel).filter(SubscriptionModel.id == sub_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="订阅不存在")
    db.delete(item)
    db.commit()
    return ApiResponse(message="删除成功")

@router.post("/subscription/{sub_id}/fetch", response_model=ApiResponse)
async def fetch_subscription(sub_id: int, db: Session = Depends(get_db)):
    async with SourceFetcher() as fetcher:
        result = await fetcher.fetch_subscription(sub_id)
    return ApiResponse(success=result["success"], message=result["message"], data=result)

# ==================== FilterRule APIs ====================

@router.get("/filter", response_model=PaginatedResponse)
async def list_filter_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    total = db.query(FilterRuleModel).count()
    items = db.query(FilterRuleModel).order_by(FilterRuleModel.order).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        data=[{k: v for k, v in item.__dict__.items() if not k.startswith("_")} for item in items],
        total=total,
        page=page,
        pageSize=page_size
    )

@router.post("/filter", response_model=ApiResponse)
async def create_filter_rule(rule: FilterRuleCreate, db: Session = Depends(get_db)):
    item = FilterRuleModel(**rule.dict())
    db.add(item)
    db.commit()
    db.refresh(item)
    return ApiResponse(data={"id": item.id}, message="创建成功")

@router.put("/filter/{rule_id}", response_model=ApiResponse)
async def update_filter_rule(rule_id: int, rule: FilterRuleCreate, db: Session = Depends(get_db)):
    item = db.query(FilterRuleModel).filter(FilterRuleModel.id == rule_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="规则不存在")
    for k, v in rule.dict().items():
        setattr(item, k, v)
    db.commit()
    return ApiResponse(message="更新成功")

@router.delete("/filter/{rule_id}", response_model=ApiResponse)
async def delete_filter_rule(rule_id: int, db: Session = Depends(get_db)):
    item = db.query(FilterRuleModel).filter(FilterRuleModel.id == rule_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="规则不存在")
    db.delete(item)
    db.commit()
    return ApiResponse(message="删除成功")
