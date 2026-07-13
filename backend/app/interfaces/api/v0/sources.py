"""
源管理接口层 (v0 - 兼容 API)

职责：
- 接收 HTTP 请求
- 调用应用层服务
- 返回统一格式响应
- 不直接操作数据库
"""

import json
from typing import Optional, List
from fastapi import APIRouter, Depends, Query

from ....core.response import ok, paginated, fail
from ....core.logging import get_logger
from ....application.services import SourceAppService
from ..dependencies import get_source_service

router = APIRouter(prefix="/api/sources", tags=["sources"])
logger = get_logger("api.sources")


# ==================== BookSource APIs ====================

@router.get("/book")
async def list_book_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: Optional[str] = None,
    group: Optional[str] = None,
    status: Optional[str] = None,
    enabled_only: bool = False,
    svc: SourceAppService = Depends(get_source_service)
):
    items, total = await svc.list_book_sources(group, status, enabled_only, page, page_size)
    
    data = []
    for item in items:
        d = item.__dict__.copy()
        d.pop("_sa_instance_state", None)
        data.append(d)
    
    return paginated(data, total, page, page_size)


@router.get("/book/{url:path}")
async def get_book_source(url: str, svc: SourceAppService = Depends(get_source_service)):
    source = await svc.get_book_source(url)
    data = source.__dict__.copy()
    data.pop("_sa_instance_state", None)
    return ok(data)


@router.post("/book")
async def create_book_source(
    source: dict,
    svc: SourceAppService = Depends(get_source_service)
):
    result = await svc.create_book_source(source)
    return ok(result.__dict__, "书源创建成功")


@router.put("/book/{url:path}")
async def update_book_source(
    url: str,
    source: dict,
    svc: SourceAppService = Depends(get_source_service)
):
    result = await svc.update_book_source(url, source)
    return ok(result.__dict__, "书源更新成功")


@router.delete("/book/{url:path}")
async def delete_book_source(url: str, svc: SourceAppService = Depends(get_source_service)):
    await svc.delete_book_source(url)
    return ok(message="书源删除成功")


@router.post("/book/import")
async def import_book_sources(
    sources: List[dict],
    svc: SourceAppService = Depends(get_source_service)
):
    from ....domain.entities.source import BookSource as BookSourceEntity
    entities = [BookSourceEntity.from_dict(s) for s in sources]
    count = await svc._repo.save_book_sources(entities)
    return ok({"count": count}, f"成功导入 {count} 个书源")


# ==================== RssSource APIs ====================

@router.get("/rss")
async def list_rss_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: Optional[str] = None,
    group: Optional[str] = None,
    status: Optional[str] = None,
    enabled_only: bool = False,
    svc: SourceAppService = Depends(get_source_service)
):
    items, total = await svc.list_rss_sources(group, status, enabled_only, page, page_size)
    data = [item.__dict__ for item in items]
    return paginated(data, total, page, page_size)


@router.get("/rss/{url:path}")
async def get_rss_source(url: str, svc: SourceAppService = Depends(get_source_service)):
    source = await svc.get_rss_source(url)
    return ok(source.__dict__)


@router.post("/rss")
async def create_rss_source(
    source: dict,
    svc: SourceAppService = Depends(get_source_service)
):
    result = await svc.create_rss_source(source)
    return ok(result.__dict__, "订阅源创建成功")


@router.delete("/rss/{url:path}")
async def delete_rss_source(url: str, svc: SourceAppService = Depends(get_source_service)):
    await svc.delete_rss_source(url)
    return ok(message="订阅源删除成功")


@router.post("/rss/import")
async def import_rss_sources(
    sources: List[dict],
    svc: SourceAppService = Depends(get_source_service)
):
    from ....domain.entities.source import RssSource as RssSourceEntity
    entities = [RssSourceEntity.from_dict(s) for s in sources]
    count = await svc._repo.save_rss_sources(entities)
    return ok({"count": count}, f"成功导入 {count} 个订阅源")


# ==================== Subscription APIs ====================

@router.get("/subscriptions")
async def list_subscriptions(svc: SourceAppService = Depends(get_source_service)):
    items = await svc.list_subscriptions()
    return ok([item.__dict__ for item in items])


@router.post("/subscriptions")
async def create_subscription(
    data: dict,
    svc: SourceAppService = Depends(get_source_service)
):
    result = await svc.create_subscription(
        name=data.get("name", ""),
        url=data.get("url", ""),
        sub_type=data.get("subType", "book")
    )
    return ok(result.__dict__, "订阅创建成功")


@router.delete("/subscriptions/{sub_id}")
async def delete_subscription(sub_id: int, svc: SourceAppService = Depends(get_source_service)):
    await svc.delete_subscription(sub_id)
    return ok(message="订阅删除成功")


# ==================== FilterRule APIs ====================

@router.get("/filters")
async def list_filter_rules(svc: SourceAppService = Depends(get_source_service)):
    items = await svc.list_filter_rules()
    return ok([item.__dict__ for item in items])


@router.post("/filters")
async def create_filter_rule(
    data: dict,
    svc: SourceAppService = Depends(get_source_service)
):
    result = await svc.create_filter_rule(data)
    return ok(result.__dict__, "规则创建成功")


@router.delete("/filters/{rule_id}")
async def delete_filter_rule(rule_id: int, svc: SourceAppService = Depends(get_source_service)):
    await svc.delete_filter_rule(rule_id)
    return ok(message="规则删除成功")


# ==================== BookSearch APIs ====================

@router.post("/book/search")
async def search_books(
    data: dict,
    svc: SourceAppService = Depends(get_source_service)
):
    """
    使用书源搜索小说

    支持搜索参数:
    - keyword: 搜索关键词（必填）
    - sourceUrl: 指定单个书源 URL（可选）
    - group: 指定书源分组（可选）
    - limit: 限制每个源返回的结果数（默认 10）
    - timeout: 搜索超时时间（默认 30s）
    """
    from ....core.exceptions import ValidationException
    from ....services.book_searcher import BookSearcher, SearchResult

    keyword = data.get("keyword", "")
    if not keyword:
        raise ValidationException("搜索关键词不能为空")

    source_url = data.get("sourceUrl")
    group = data.get("group")
    limit = data.get("limit", 10)
    timeout = data.get("timeout", 30)

    # 获取书源列表
    if source_url:
        source_data = await svc.get_book_source(source_url)
        sources = [source_data]
    else:
        items, total = await svc.list_book_sources(group=group, status="ok", enabled_only=True, page=1, page_size=200)
        sources = items

    # 逐源搜索（可并发优化，但为了稳定性顺序执行）
    all_results = []
    errors = []

    for source in sources:
        if not source.searchUrl or not source.ruleSearch:
            continue

        try:
            searcher = BookSearcher(source)
            results = await searcher.search(keyword, timeout=timeout)
            all_results.extend(results[:limit])
        except Exception as e:
            logger.warning(
                f"[BookSearch] 书源搜索异常: {source.bookSourceName} - {type(e).__name__}: {e}",
                extra={"action": "book_search_api", "source_name": source.bookSourceName, "error": str(e)}
            )
            errors.append({
                "source": source.bookSourceName,
                "url": source.bookSourceUrl,
                "error": str(e),
            })

    return ok({
        "keyword": keyword,
        "total": len(all_results),
        "sources_searched": len(sources),
        "errors": len(errors),
        "results": [
            {
                "name": r.name,
                "author": r.author,
                "bookUrl": r.bookUrl,
                "intro": r.intro,
                "coverUrl": r.coverUrl,
                "lastChapter": r.lastChapter,
                "kind": r.kind,
                "sourceName": r.sourceName,
                "sourceUrl": r.sourceUrl,
            }
            for r in all_results
        ],
        "errors": errors[:20],  # 最多返回20个错误
    })
