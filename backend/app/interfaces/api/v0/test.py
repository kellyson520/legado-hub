"""
书源测试接口层 (v0)

提供书源的完整链路测试、目录预览、正文预览等功能
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException

from ....core.response import ok, fail
from ....core.logging import get_logger
from ....application.services import SourceAppService
from ..dependencies import get_source_service
from ....infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher

router = APIRouter(prefix="/api/test", tags=["test"])
logger = get_logger("api.test")


@router.post("/search")
async def test_search(
    data: dict,
    svc: SourceAppService = Depends(get_source_service),
):
    """
    测试书源搜索功能

    Request Body:
      - sourceUrl: 书源 URL
      - keyword: 搜索关键词
      - timeout: 超时时间（秒）
    """
    source_url = data.get("sourceUrl", "")
    keyword = data.get("keyword", "")
    timeout = data.get("timeout", 30)

    if not source_url:
        return fail("书源 URL 不能为空")
    if not keyword:
        return fail("搜索关键词不能为空")

    try:
        source = await svc.get_book_source(source_url)
    except Exception:
        return fail("书源不存在")

    source_dict = source.__dict__.copy()
    source_dict.pop("_sa_instance_state", None)

    fetcher = LegadoBookSourceFetcher(timeout=timeout)
    try:
        results = await fetcher.search(source_dict, keyword)
        return ok({
            "sourceName": source_dict.get("bookSourceName", ""),
            "sourceUrl": source_url,
            "keyword": keyword,
            "count": len(results),
            "results": results[:20],
        }, f"搜索成功，共 {len(results)} 条结果")
    except Exception as e:
        logger.error(f"搜索测试失败: {e}")
        return fail(f"搜索失败: {str(e)}")
    finally:
        await fetcher.close()


@router.post("/toc")
async def test_toc(
    data: dict,
    svc: SourceAppService = Depends(get_source_service),
):
    """
    测试书源目录获取功能

    Request Body:
      - sourceUrl: 书源 URL
      - bookUrl: 书籍详情页 URL
      - timeout: 超时时间（秒）
    """
    source_url = data.get("sourceUrl", "")
    book_url = data.get("bookUrl", "")
    timeout = data.get("timeout", 30)

    if not source_url:
        return fail("书源 URL 不能为空")
    if not book_url:
        return fail("书籍 URL 不能为空")

    try:
        source = await svc.get_book_source(source_url)
    except Exception:
        return fail("书源不存在")

    source_dict = source.__dict__.copy()
    source_dict.pop("_sa_instance_state", None)

    fetcher = LegadoBookSourceFetcher(timeout=timeout)
    try:
        chapters = await fetcher.get_toc(source_dict, book_url)
        return ok({
            "sourceName": source_dict.get("bookSourceName", ""),
            "bookUrl": book_url,
            "count": len(chapters),
            "chapters": [
                {
                    "index": c.get("index", i),
                    "title": c.get("title", ""),
                    "url": c.get("url", ""),
                }
                for i, c in enumerate(chapters[:50])
            ],
        }, f"目录获取成功，共 {len(chapters)} 章")
    except Exception as e:
        logger.error(f"目录测试失败: {e}")
        return fail(f"目录获取失败: {str(e)}")
    finally:
        await fetcher.close()


@router.post("/content")
async def test_content(
    data: dict,
    svc: SourceAppService = Depends(get_source_service),
):
    """
    测试书源正文获取功能

    Request Body:
      - sourceUrl: 书源 URL
      - chapterUrl: 章节 URL
      - timeout: 超时时间（秒）
    """
    source_url = data.get("sourceUrl", "")
    chapter_url = data.get("chapterUrl", "")
    timeout = data.get("timeout", 30)

    if not source_url:
        return fail("书源 URL 不能为空")
    if not chapter_url:
        return fail("章节 URL 不能为空")

    try:
        source = await svc.get_book_source(source_url)
    except Exception:
        return fail("书源不存在")

    source_dict = source.__dict__.copy()
    source_dict.pop("_sa_instance_state", None)

    fetcher = LegadoBookSourceFetcher(timeout=timeout)
    try:
        result = await fetcher.get_content(source_dict, chapter_url)
        content = result.get("content", "")
        word_count = len(content.replace("\n", "").replace(" ", ""))

        return ok({
            "sourceName": source_dict.get("bookSourceName", ""),
            "chapterUrl": chapter_url,
            "title": result.get("title", ""),
            "content": content[:2000] + ("..." if len(content) > 2000 else ""),
            "wordCount": word_count,
            "nextUrl": result.get("nextUrl", ""),
            "fullLength": len(content),
        }, f"正文获取成功，共 {word_count} 字")
    except Exception as e:
        logger.error(f"正文测试失败: {e}")
        return fail(f"正文获取失败: {str(e)}")
    finally:
        await fetcher.close()


@router.post("/full")
async def test_full(
    data: dict,
    svc: SourceAppService = Depends(get_source_service),
):
    """
    完整链路测试：搜索 -> 目录 -> 正文

    Request Body:
      - sourceUrl: 书源 URL
      - keyword: 搜索关键词
      - timeout: 超时时间（秒）
    """
    source_url = data.get("sourceUrl", "")
    keyword = data.get("keyword", "斗罗大陆")
    timeout = data.get("timeout", 30)

    if not source_url:
        return fail("书源 URL 不能为空")

    try:
        source = await svc.get_book_source(source_url)
    except Exception:
        return fail("书源不存在")

    source_dict = source.__dict__.copy()
    source_dict.pop("_sa_instance_state", None)

    fetcher = LegadoBookSourceFetcher(timeout=timeout)
    results = {
        "sourceName": source_dict.get("bookSourceName", ""),
        "sourceUrl": source_url,
        "search": {"success": False, "count": 0, "error": ""},
        "toc": {"success": False, "count": 0, "error": ""},
        "content": {"success": False, "wordCount": 0, "error": ""},
    }

    try:
        # 步骤1: 搜索
        search_results = await fetcher.search(source_dict, keyword)
        results["search"]["success"] = True
        results["search"]["count"] = len(search_results)

        if not search_results:
            results["search"]["error"] = "无搜索结果"
            return ok(results, "搜索测试完成")

        first_book = search_results[0]
        book_url = first_book.get("bookUrl", "")
        results["search"]["firstBook"] = {
            "name": first_book.get("name", ""),
            "author": first_book.get("author", ""),
            "bookUrl": book_url,
        }

        # 步骤2: 目录
        try:
            chapters = await fetcher.get_toc(source_dict, book_url)
            results["toc"]["success"] = True
            results["toc"]["count"] = len(chapters)

            if chapters:
                first_chapter = chapters[0]
                results["toc"]["firstChapter"] = {
                    "title": first_chapter.get("title", ""),
                    "url": first_chapter.get("url", ""),
                }

                # 步骤3: 正文
                try:
                    content_result = await fetcher.get_content(
                        source_dict, first_chapter.get("url", "")
                    )
                    content = content_result.get("content", "")
                    word_count = len(content.replace("\n", "").replace(" ", ""))
                    results["content"]["success"] = True
                    results["content"]["wordCount"] = word_count
                    results["content"]["title"] = content_result.get("title", "")
                    results["content"]["preview"] = content[:200] + ("..." if len(content) > 200 else "")
                except Exception as e:
                    results["content"]["error"] = str(e)
            else:
                results["toc"]["error"] = "无章节列表"
        except Exception as e:
            results["toc"]["error"] = str(e)

    except Exception as e:
        results["search"]["error"] = str(e)
    finally:
        await fetcher.close()

    # 计算总体评分
    score = 0
    if results["search"]["success"] and results["search"]["count"] > 0:
        score += 40
    if results["toc"]["success"] and results["toc"]["count"] > 0:
        score += 30
    if results["content"]["success"] and results["content"]["wordCount"] > 100:
        score += 30
    results["score"] = score

    status = "完美" if score >= 90 else ("良好" if score >= 60 else ("一般" if score >= 30 else "失败"))
    results["status"] = status

    return ok(results, f"完整测试完成，评分: {score}/100 ({status})")
