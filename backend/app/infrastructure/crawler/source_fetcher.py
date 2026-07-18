"""
爬虫引擎 - 订阅源拉取与可用性检查

职责：
- 异步拉取订阅链接并解析源数据
- 可用性检查（带连接池复用）
- 规则过滤
- 全链路日志追踪
- 发布领域事件
"""

import json
import re
import asyncio
import time
import aiohttp
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.core.exceptions import ExternalServiceException, ValidationException
from app.core.events import publish_event, SourceFetchedEvent, FilterRuleTriggeredEvent
from app.domain.repositories.source_repo import SourceRepository

logger = get_logger("engine.fetcher")


class CrawlerPool:
    """
    连接池管理 - 复用 HTTP 会话，避免频繁创建连接

    小 VPS 优化：
    - 限制最大连接数（默认 10）
    - TCPConnector 复用
    - 自动清理
    """

    _session: Optional[aiohttp.ClientSession] = None
    _ref_count: int = 0
    _lock: asyncio.Lock = asyncio.Lock()

    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    @classmethod
    async def acquire(cls, timeout: int = 30) -> aiohttp.ClientSession:
        """获取共享会话"""
        async with cls._lock:
            if cls._session is None or cls._session.closed:
                connector = aiohttp.TCPConnector(
                    limit=10,  # 最大 10 个并发连接（小 VPS 友好）
                    limit_per_host=5,
                    ttl_dns_cache=300,
                    force_close=False,
                )
                cls._session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=aiohttp.ClientTimeout(total=timeout, connect=10),
                    headers=cls.DEFAULT_HEADERS,
                )
                logger.info("[CrawlerPool] 创建共享连接池")
            cls._ref_count += 1
            return cls._session

    @classmethod
    async def release(cls):
        """释放引用（引用计数归零时关闭）"""
        async with cls._lock:
            cls._ref_count = max(0, cls._ref_count - 1)
            if cls._ref_count == 0 and cls._session and not cls._session.closed:
                await cls._session.close()
                cls._session = None
                logger.info("[CrawlerPool] 连接池已关闭")


class SourceFetcher:
    """订阅源拉取与处理服务"""

    def __init__(self, source_repository: SourceRepository | None = None):
        self._session: Optional[aiohttp.ClientSession] = None
        self._source_repository = source_repository

    async def __aenter__(self):
        self._session = await CrawlerPool.acquire(timeout=30)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await CrawlerPool.release()
        self._session = None

    async def fetch_url(self, url: str, timeout: int = 30) -> Tuple[int, str]:
        """
        拉取 URL 内容，返回 (status_code, body_text)

        日志：记录每个请求的 URL、耗时、状态码
        异常：连接失败/超时/HTTP 错误均有明确日志
        """
        if not url:
            raise ValidationException("URL 不能为空")

        start = time.time()
        logger.debug(f"[Fetch] 开始拉取: {url}")

        try:
            async with self._session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                elapsed_ms = (time.time() - start) * 1000
                status = resp.status
                text = await resp.text(errors="replace")

                if status == 200:
                    logger.info(
                        f"[Fetch] 拉取成功: {url}",
                        extra={
                            "action": "fetch_url",
                            "source_url": url,
                            "status_code": status,
                            "duration_ms": round(elapsed_ms, 2),
                            "content_length": len(text),
                        }
                    )
                elif 400 <= status < 500:
                    logger.warning(
                        f"[Fetch] 客户端错误: {url} HTTP {status}",
                        extra={"action": "fetch_url", "source_url": url, "status_code": status, "duration_ms": round(elapsed_ms, 2)}
                    )
                else:
                    logger.error(
                        f"[Fetch] 服务端错误: {url} HTTP {status}",
                        extra={"action": "fetch_url", "source_url": url, "status_code": status, "duration_ms": round(elapsed_ms, 2)}
                    )

                return status, text

        except asyncio.TimeoutError:
            elapsed_ms = (time.time() - start) * 1000
            logger.error(
                f"[Fetch] 超时: {url} ({timeout}s)",
                extra={"action": "fetch_url", "source_url": url, "duration_ms": round(elapsed_ms, 2), "error": "timeout"}
            )
            return 0, f"请求超时 ({timeout}s)"

        except aiohttp.ClientConnectorError as e:
            elapsed_ms = (time.time() - start) * 1000
            logger.error(
                f"[Fetch] 连接失败: {url} - {type(e).__name__}: {e}",
                extra={"action": "fetch_url", "source_url": url, "duration_ms": round(elapsed_ms, 2), "error": str(e)}
            )
            return 0, f"连接失败: {e}"

        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            logger.error(
                f"[Fetch] 未知错误: {url} - {type(e).__name__}: {e}",
                extra={"action": "fetch_url", "source_url": url, "duration_ms": round(elapsed_ms, 2), "error": str(e)},
                exc_info=True
            )
            return 0, f"拉取异常: {e}"

    def parse_sources_from_text(self, text: str, origin: str = "") -> Tuple[List[Dict], List[Dict]]:
        """
        从文本中解析书源和订阅源

        日志：记录解析数量、JSON 解析失败次数
        """
        text = text.strip()
        if not text:
            logger.warning(f"[Parse] 空内容, origin={origin}")
            return [], []

        book_sources = []
        rss_sources = []
        json_errors = 0

        # 尝试整体 JSON 解析
        try:
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    self._classify_source(item, book_sources, rss_sources, origin)
            elif isinstance(data, dict):
                self._classify_source(data, book_sources, rss_sources, origin)
            logger.info(
                f"[Parse] JSON 解析完成: origin={origin}, 书源={len(book_sources)}, 订阅源={len(rss_sources)}",
                extra={"action": "parse_sources", "source_url": origin}
            )
            return book_sources, rss_sources
        except json.JSONDecodeError:
            pass

        # 尝试每行一个 JSON（NDJSON 格式）
        for line_num, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                self._classify_source(item, book_sources, rss_sources, origin)
            except json.JSONDecodeError as e:
                json_errors += 1
                if json_errors <= 3:  # 只记录前 3 个
                    logger.debug(f"[Parse] 第 {line_num} 行 JSON 解析失败: {e}")

        if json_errors > 0:
            logger.warning(
                f"[Parse] NDJSON 解析完成, 共 {json_errors} 行失败: origin={origin}, 书源={len(book_sources)}, 订阅源={len(rss_sources)}",
                extra={"action": "parse_sources", "source_url": origin, "json_errors": json_errors}
            )
        else:
            logger.info(
                f"[Parse] NDJSON 解析完成: origin={origin}, 书源={len(book_sources)}, 订阅源={len(rss_sources)}",
                extra={"action": "parse_sources", "source_url": origin}
            )

        return book_sources, rss_sources

    def _classify_source(self, item: Dict, book_sources: List, rss_sources: List, origin: str):
        """分类单个源"""
        if not isinstance(item, dict):
            return
        item["sourceOrigin"] = origin
        if "bookSourceUrl" in item:
            book_sources.append(item)
        elif "sourceUrl" in item and "bookSourceUrl" not in item:
            rss_sources.append(item)
        elif "searchUrl" in item and "bookSourceName" not in item:
            rss_sources.append(item)

    async def fetch_subscription(self, sub_id: int) -> Dict[str, Any]:
        """
        拉取单个订阅（完整流程）

        日志覆盖：拉取 -> 解析 -> 过滤 -> 保存 -> 事件发布
        异常覆盖：网络失败 / JSON 解析失败 / DB 保存失败 / 过滤异常
        """
        from app.domain.entities.source import BookSource, RssSource

        repo = self._source_repository
        if repo is None:
            raise ValidationException("source repository is not configured")

        try:
            # 1. 获取订阅信息
            subs = await repo.list_subscriptions()
            sub = next((s for s in subs if s.id == sub_id), None)
            if not sub:
                logger.warning(f"[FetchSub] 订阅不存在: id={sub_id}", extra={"action": "fetch_sub", "sub_id": sub_id})
                return {"success": False, "message": f"订阅不存在: id={sub_id}"}

            logger.info(
                f"[FetchSub] 开始拉取: {sub.name} ({sub.url})",
                extra={"action": "fetch_sub", "sub_id": sub_id, "source_url": sub.url}
            )

            # 2. 拉取内容
            status_code, text = await self.fetch_url(sub.url)
            if status_code != 200:
                logger.error(
                    f"[FetchSub] 拉取失败: {sub.name} HTTP {status_code}",
                    extra={"action": "fetch_sub", "sub_id": sub_id, "status_code": status_code}
                )
                return {"success": False, "message": f"拉取失败: HTTP {status_code}"}

            # 3. 解析源
            book_sources_raw, rss_sources_raw = self.parse_sources_from_text(text, sub.url)

            # 4. 过滤
            book_entities = [BookSource.from_dict(s) for s in book_sources_raw]
            rss_entities = [RssSource.from_dict(s) for s in rss_sources_raw]

            rules = await repo.list_filter_rules(enabled_only=True)
            filtered_books = await self._apply_filters(book_entities, rules, "book")
            filtered_rss = await self._apply_filters(rss_entities, rules, "rss")

            filtered_out = (len(book_entities) - len(filtered_books)) + (len(rss_entities) - len(filtered_rss))
            if filtered_out > 0:
                logger.info(
                    f"[FetchSub] 过滤掉 {filtered_out} 个源",
                    extra={"action": "filter", "sub_id": sub_id, "filtered_count": filtered_out}
                )

            # 5. 保存
            saved_books = await repo.save_book_sources(filtered_books)
            saved_rss = await repo.save_rss_sources(filtered_rss)

            # 6. 更新订阅状态
            sub.mark_fetched(saved_books + saved_rss)
            await repo.save_subscription(sub)

            # 7. 发布领域事件
            await publish_event(SourceFetchedEvent(
                subscription_id=sub_id,
                subscription_name=sub.name,
                book_count=saved_books,
                rss_count=saved_rss,
                status="success",
                message=f"书源 {saved_books}, 订阅源 {saved_rss}"
            ))

            result_msg = f"拉取完成: 书源 {saved_books} 个, 订阅源 {saved_rss} 个"
            logger.info(
                f"[FetchSub] {result_msg}",
                extra={"action": "fetch_sub", "sub_id": sub_id, "book_count": saved_books, "rss_count": saved_rss}
            )

            return {
                "success": True,
                "message": result_msg,
                "bookSources": saved_books,
                "rssSources": saved_rss,
            }

        except ExternalServiceException:
            raise
        except Exception as e:
            logger.error(
                f"[FetchSub] 拉取异常: id={sub_id} - {type(e).__name__}: {e}",
                extra={"action": "fetch_sub", "sub_id": sub_id, "error": str(e)},
                exc_info=True
            )

            # 发布失败事件
            try:
                await publish_event(SourceFetchedEvent(
                    subscription_id=sub_id,
                    subscription_name="",
                    status="error",
                    message=str(e)[:200]
                ))
            except Exception:
                pass  # 事件发布失败不影响主流程

            return {"success": False, "message": f"拉取异常: {type(e).__name__}: {e}"}

    async def _apply_filters(self, sources: list, rules: list, source_type: str) -> list:
        """应用过滤规则（异步 + 日志）"""
        filtered = []
        for source in sources:
            keep = True
            for rule in rules:
                if not source.should_filter(
                    source_name=getattr(source, "bookSourceName" if source_type == "book" else "sourceName", "") or "",
                    source_url=getattr(source, "bookSourceUrl" if source_type == "book" else "sourceUrl", "") or "",
                    source_group=getattr(source, "bookSourceGroup" if source_type == "book" else "sourceGroup", "") or "",
                ):
                    keep = False
                    logger.debug(
                        f"[Filter] 规则 [{rule.name}] 过滤: {getattr(source, 'bookSourceName' if source_type == 'book' else 'sourceName', '')}",
                        extra={"action": "filter_triggered", "rule_id": rule.id, "rule_name": rule.name}
                    )
                    break
            if keep:
                filtered.append(source)
        return filtered


class SourceChecker:
    """源可用性检查服务（复用连接池）"""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = await CrawlerPool.acquire(timeout=15)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await CrawlerPool.release()
        self._session = None

    async def check_book_source(self, source: Dict) -> Dict[str, Any]:
        """检查书源可用性"""
        url = source.get("bookSourceUrl", "")
        name = source.get("bookSourceName", "未知")

        if not url:
            logger.warning("[Check] 书源 URL 为空", extra={"action": "check_source", "source_name": name})
            return {"status": "error", "errorMsg": "URL 为空", "responseTime": 0}

        start = time.time()
        try:
            async with self._session.get(url, ssl=False) as resp:
                elapsed = (time.time() - start) * 1000
                if resp.status < 400:
                    logger.info(
                        f"[Check] 书源正常: {name} ({resp.status}, {elapsed:.0f}ms)",
                        extra={"action": "check_source", "source_url": url, "status": "ok", "duration_ms": round(elapsed, 2)}
                    )
                    return {"status": "ok", "responseTime": elapsed, "errorMsg": None}
                else:
                    logger.warning(
                        f"[Check] 书源异常: {name} HTTP {resp.status} ({elapsed:.0f}ms)",
                        extra={"action": "check_source", "source_url": url, "status": "error", "status_code": resp.status, "duration_ms": round(elapsed, 2)}
                    )
                    return {"status": "error", "responseTime": elapsed, "errorMsg": f"HTTP {resp.status}"}
        except asyncio.TimeoutError:
            elapsed = (time.time() - start) * 1000
            logger.error(
                f"[Check] 书源超时: {name} ({elapsed:.0f}ms)",
                extra={"action": "check_source", "source_url": url, "status": "error", "error": "timeout", "duration_ms": round(elapsed, 2)}
            )
            return {"status": "error", "responseTime": elapsed, "errorMsg": "请求超时"}
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(
                f"[Check] 书源检查异常: {name} - {type(e).__name__}: {e}",
                extra={"action": "check_source", "source_url": url, "status": "error", "error": str(e), "duration_ms": round(elapsed, 2)},
                exc_info=True
            )
            return {"status": "error", "responseTime": elapsed, "errorMsg": str(e)[:200]}

    async def check_rss_source(self, source: Dict) -> Dict[str, Any]:
        """检查订阅源可用性"""
        url = source.get("sourceUrl", "")
        name = source.get("sourceName", "未知")

        if not url:
            return {"status": "error", "errorMsg": "URL 为空", "responseTime": 0}

        start = time.time()
        try:
            async with self._session.get(url, ssl=False) as resp:
                elapsed = (time.time() - start) * 1000
                text = await resp.text()

                if resp.status >= 400:
                    logger.warning(
                        f"[Check] 订阅源异常: {name} HTTP {resp.status}",
                        extra={"action": "check_source", "source_url": url, "status": "error", "status_code": resp.status, "duration_ms": round(elapsed, 2)}
                    )
                    return {"status": "error", "responseTime": elapsed, "errorMsg": f"HTTP {resp.status}"}

                # 尝试解析
                import feedparser
                feed = feedparser.parse(text)
                if feed.entries or feed.feed:
                    logger.info(
                        f"[Check] 订阅源正常: {name} (RSS, {elapsed:.0f}ms)",
                        extra={"action": "check_source", "source_url": url, "status": "ok", "duration_ms": round(elapsed, 2)}
                    )
                    return {"status": "ok", "responseTime": elapsed, "errorMsg": None}

                if "<html" in text.lower():
                    logger.info(
                        f"[Check] 订阅源正常: {name} (HTML, {elapsed:.0f}ms)",
                        extra={"action": "check_source", "source_url": url, "status": "ok", "duration_ms": round(elapsed, 2)}
                    )
                    return {"status": "ok", "responseTime": elapsed, "errorMsg": None}

                logger.warning(
                    f"[Check] 订阅源无法识别: {name}",
                    extra={"action": "check_source", "source_url": url, "status": "error", "duration_ms": round(elapsed, 2)}
                )
                return {"status": "error", "responseTime": elapsed, "errorMsg": "无法识别 RSS 内容"}

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(
                f"[Check] 订阅源异常: {name} - {type(e).__name__}: {e}",
                extra={"action": "check_source", "source_url": url, "status": "error", "error": str(e), "duration_ms": round(elapsed, 2)},
                exc_info=True
            )
            return {"status": "error", "responseTime": elapsed, "errorMsg": str(e)[:200]}
