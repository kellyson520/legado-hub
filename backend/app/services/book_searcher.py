"""
书源搜索服务 - 利用书源规则搜索小说

依赖：beautifulsoup4, lxml
安装：pip install beautifulsoup4 lxml

职责：
- 解析 searchUrl（支持 GET/POST、charset、method 等选项）
- 替换关键词占位符 {{key}}, {key}, {{keyword}}, searchKey 等
- 发起搜索 HTTP 请求
- 用简易规则引擎解析搜索结果（支持 CSS 选择器子集 + JSONPath 子集）
- 返回结构化搜索结果列表
"""

import asyncio
import json
import time
import aiohttp
from dataclasses import dataclass
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from ..core.logging import get_logger
from .fetcher import CrawlerPool

logger = get_logger("engine.searcher")


@dataclass
class SearchResult:
    """单条搜索结果"""
    name: str = ""
    author: str = ""
    bookUrl: str = ""
    intro: str = ""
    coverUrl: str = ""
    lastChapter: str = ""
    kind: str = ""
    sourceName: str = ""
    sourceUrl: str = ""


class BookSearcher:
    """书源搜索器"""

    def __init__(self, source):
        """
        初始化搜索器

        Args:
            source: BookSource 领域实体实例
        """
        self._source = source

    async def search(self, keyword: str, timeout: int = 30) -> List[SearchResult]:
        """
        使用书源搜索关键词

        Args:
            keyword: 搜索关键词
            timeout: 超时时间（秒）

        Returns:
            搜索结果列表
        """
        if not self._source.searchUrl or not self._source.ruleSearch:
            return []

        # 1. 解析 searchUrl
        parsed = self._parse_search_url(self._source.searchUrl)

        # 2. 如果是相对路径，拼接 baseUrl
        url = parsed["url"]
        if url.startswith("/"):
            url = self._source.bookSourceUrl.rstrip("/") + url

        # 3. HTTP 请求
        try:
            status, text = await self._search_http(url, keyword, parsed["options"], timeout)
        except Exception as e:
            logger.error(
                f"[BookSearch] {self._source.bookSourceName} 搜索 '{keyword}' 请求异常: {type(e).__name__}: {e}",
                extra={"action": "book_search", "source_url": self._source.bookSourceUrl, "error": str(e)}
            )
            return []

        if status != 200 or not text:
            return []

        # 4. 判断响应类型并解析
        book_list = self._source.ruleSearch.get("bookList", "")
        items = []

        try:
            if book_list and book_list.startswith("$"):
                # JSONPath 模式
                items = self._parse_json(text, self._source.ruleSearch)
            else:
                # CSS 选择器模式
                items = self._parse_html(text, self._source.ruleSearch)
        except Exception as e:
            logger.error(
                f"[BookSearch] {self._source.bookSourceName} 搜索 '{keyword}' 解析异常: {type(e).__name__}: {e}",
                extra={"action": "book_search_parse", "source_url": self._source.bookSourceUrl, "error": str(e)},
                exc_info=True
            )
            return []

        # 5. 包装结果
        results = []
        for item in items:
            result = SearchResult(
                name=item.get("name", ""),
                author=item.get("author", ""),
                bookUrl=item.get("bookUrl", ""),
                intro=item.get("intro", ""),
                coverUrl=item.get("coverUrl", ""),
                lastChapter=item.get("lastChapter", ""),
                kind=item.get("kind", ""),
                sourceName=self._source.bookSourceName,
                sourceUrl=self._source.bookSourceUrl,
            )
            if result.name or result.bookUrl:
                results.append(result)

        logger.info(
            f"[BookSearch] {self._source.bookSourceName} 搜索 '{keyword}': {len(results)} 条结果",
            extra={"action": "book_search", "source_name": self._source.bookSourceName, "keyword": keyword, "result_count": len(results)}
        )
        return results

    # ==================== searchUrl 解析 ====================

    def _parse_search_url(self, search_url: str) -> dict:
        """解析 Legado searchUrl 格式: URL{,{option1},{option2},...}"""
        parts = search_url.split(",")
        url = parts[0].strip()
        options = {}
        for part in parts[1:]:
            part = part.strip().strip("{").strip("}")
            if ":" in part:
                key, val = part.split(":", 1)
                options[key.strip().strip('"')] = val.strip().strip('"')
        return {"url": url, "options": options}

    # ==================== 关键词替换 ====================

    def _replace_keyword(self, url: str, keyword: str) -> str:
        """替换关键词占位符"""
        return (
            url
            .replace("{{key}}", keyword)
            .replace("{key}", keyword)
            .replace("{{keyword}}", keyword)
            .replace("{keyword}", keyword)
        )

    # ==================== HTTP 请求 ====================

    async def _search_http(
        self, base_url: str, keyword: str, options: dict, timeout: int = 30
    ) -> Tuple[int, str]:
        """发起搜索 HTTP 请求"""
        search_url = self._replace_keyword(base_url, keyword)

        method = options.get("method", "GET").upper()
        charset = options.get("charset", "utf-8")

        headers = dict(CrawlerPool.DEFAULT_HEADERS)
        if self._source.header:
            try:
                header_dict = json.loads(self._source.header)
                headers.update(header_dict)
            except (json.JSONDecodeError, TypeError):
                headers["User-Agent"] = self._source.header

        start = time.time()
        try:
            session = await CrawlerPool.acquire(timeout)
            try:
                if method == "POST":
                    body = options.get("body", "")
                    body = self._replace_keyword(body, keyword)
                    async with session.post(
                        search_url,
                        data=body.encode(charset, errors="replace"),
                        headers=headers,
                        ssl=False,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as resp:
                        raw = await resp.read()
                        text = raw.decode(charset, errors="replace")
                        elapsed_ms = (time.time() - start) * 1000
                        logger.debug(
                            f"[BookSearch] POST 请求完成: {search_url} HTTP {resp.status} ({elapsed_ms:.0f}ms)",
                            extra={"action": "book_search_http", "method": "POST", "status_code": resp.status, "duration_ms": round(elapsed_ms, 2)}
                        )
                        return resp.status, text
                else:
                    async with session.get(
                        search_url,
                        headers=headers,
                        ssl=False,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as resp:
                        raw = await resp.read()
                        text = raw.decode(charset, errors="replace")
                        elapsed_ms = (time.time() - start) * 1000
                        logger.debug(
                            f"[BookSearch] GET 请求完成: {search_url} HTTP {resp.status} ({elapsed_ms:.0f}ms)",
                            extra={"action": "book_search_http", "method": "GET", "status_code": resp.status, "duration_ms": round(elapsed_ms, 2)}
                        )
                        return resp.status, text
            finally:
                await CrawlerPool.release()

        except asyncio.TimeoutError:
            elapsed_ms = (time.time() - start) * 1000
            logger.warning(
                f"[BookSearch] 请求超时: {search_url} ({timeout}s)",
                extra={"action": "book_search_http", "error": "timeout", "duration_ms": round(elapsed_ms, 2)}
            )
            return 0, f"请求超时 ({timeout}s)"

        except aiohttp.ClientConnectorError as e:
            elapsed_ms = (time.time() - start) * 1000
            logger.warning(
                f"[BookSearch] 连接失败: {search_url} - {type(e).__name__}: {e}",
                extra={"action": "book_search_http", "error": str(e), "duration_ms": round(elapsed_ms, 2)}
            )
            return 0, f"连接失败: {e}"

        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            logger.error(
                f"[BookSearch] 请求异常: {search_url} - {type(e).__name__}: {e}",
                extra={"action": "book_search_http", "error": str(e), "duration_ms": round(elapsed_ms, 2)},
                exc_info=True
            )
            return 0, f"请求异常: {e}"

    # ==================== JSONPath 解析（模式 A）====================

    def _parse_json(self, text: str, rule_search: dict) -> list:
        """用 JSONPath 解析 JSON 响应"""
        data = json.loads(text)

        # 获取书籍列表
        book_list_expr = rule_search.get("bookList", "")
        books = self._simple_jsonpath(data, book_list_expr)

        if not books or not isinstance(books, list):
            return []

        results = []
        for book in books:
            try:
                result = {
                    "name": self._simple_jsonpath(book, rule_search.get("name", "")),
                    "author": self._simple_jsonpath(book, rule_search.get("author", "")),
                    "bookUrl": self._simple_jsonpath(book, rule_search.get("bookUrl", "")),
                    "intro": self._simple_jsonpath(book, rule_search.get("intro", "")),
                    "coverUrl": self._simple_jsonpath(book, rule_search.get("coverUrl", "")),
                    "lastChapter": self._simple_jsonpath(book, rule_search.get("lastChapter", "")),
                    "kind": self._simple_jsonpath(book, rule_search.get("kind", "")),
                }
                # 清洗 null 值：如果值是列表取第一个，然后过滤空值
                result = {
                    k: (v[0] if isinstance(v, list) and v else v)
                    for k, v in result.items()
                }
                result = {
                    k: (str(v) if v is not None else v)
                    for k, v in result.items()
                }
                result = {k: v for k, v in result.items() if v is not None and v != ""}
                results.append(result)
            except Exception as e:
                logger.debug(
                    f"[BookSearch] JSON 解析单条异常: {e}",
                    extra={"action": "book_search_json_parse", "error": str(e)}
                )
                continue

        return results

    def _simple_jsonpath(self, data, expr: str):
        """
        简易 JSONPath 实现（支持 $.field, $..field, $.field1&&$.field2）

        支持 Legado 后缀：
        - @text, @put:{...} 会被剥离
        - ##xxx 正则后缀会被剥离
        """
        if not expr:
            return None

        # 去掉 Legado 后缀 @text, @put:{...}, ##xxx
        clean_expr = expr.split("@")[0].split("##")[0].strip()

        if not clean_expr:
            return None

        # && 分隔符：取第一个有值的结果
        for sub in clean_expr.split("&&"):
            sub = sub.strip()
            if not sub:
                continue
            result = self._eval_jsonpath(data, sub)
            if result is not None:
                return result
        return None

    def _eval_jsonpath(self, data, expr: str):
        """执行单条 JSONPath 表达式"""
        if expr.startswith("$.."):
            # 递归查找
            key = expr[3:]
            return self._recursive_find(data, key)
        elif expr.startswith("$."):
            key = expr[2:]
            if "{" in key:
                # 模板字符串 如 $.Name@put:{a:$.Id}，暂不处理
                return None
            return data.get(key) if isinstance(data, dict) else None
        return None

    def _recursive_find(self, data, key: str):
        """递归查找字典中的 key"""
        if isinstance(data, dict):
            for k, v in data.items():
                if k == key:
                    return v
                result = self._recursive_find(v, key)
                if result is not None:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._recursive_find(item, key)
                if result is not None:
                    return result
        return None

    # ==================== HTML CSS 选择器解析（模式 B）====================

    def _parse_html(self, text: str, rule_search: dict) -> list:
        """用 CSS 选择器解析 HTML 响应"""
        soup = BeautifulSoup(text, "lxml")
        book_list_expr = rule_search.get("bookList", "")

        if not book_list_expr:
            return []

        # 支持 || 分隔符：尝试多个选择器
        books_elements = []
        for selector in book_list_expr.split("||"):
            selector = selector.strip()
            if not selector:
                continue
            elements = self._css_select(soup, selector)
            if elements:
                books_elements = elements
                break

        results = []
        for element in books_elements:
            try:
                result = {
                    "name": self._extract_field(element, rule_search.get("name", "")),
                    "author": self._extract_field(element, rule_search.get("author", "")),
                    "bookUrl": self._extract_field(element, rule_search.get("bookUrl", "")),
                    "intro": self._extract_field(element, rule_search.get("intro", "")),
                    "coverUrl": self._extract_field(element, rule_search.get("coverUrl", "")),
                    "lastChapter": self._extract_field(element, rule_search.get("lastChapter", "")),
                    "kind": self._extract_field(element, rule_search.get("kind", "")),
                }
                result = {k: v for k, v in result.items() if v is not None and v != ""}
                if result.get("name") or result.get("bookUrl"):
                    results.append(result)
            except Exception as e:
                logger.debug(
                    f"[BookSearch] HTML 解析单条异常: {e}",
                    extra={"action": "book_search_html_parse", "error": str(e)}
                )
                continue

        return results

    def _extract_field(self, element, rule: str) -> Optional[str]:
        """从 HTML 元素中提取字段值（支持 Legado 规则子集）"""
        if not rule:
            return None

        for sub in rule.split("||"):
            sub = sub.strip()
            if not sub:
                continue

            # 去掉 ##xxx 正则后缀
            clean = sub.split("##")[0].strip()

            value = self._eval_css_rule(element, clean)
            if value:
                return value
        return None

    def _eval_css_rule(self, element, rule: str) -> Optional[str]:
        """
        执行 CSS 规则，支持：
        - class.name -> element.select_one(".name")
        - id.content -> element.select_one("#content")
        - tag.a -> element.select_one("a")
        - tag.img@src -> element.select_one("img")["src"]
        - tag.h3@text -> element.select_one("h3").get_text()
        - class.s1@tag.a.0@href -> element.select_one(".s1").select("a")[0]["href"]
        """
        if not rule:
            return None

        # 分步解析：tag.selector1.selector2@indexN@attr
        parts = rule.split("@")
        selectors = parts[0]
        result_element = self._css_select_one(element, selectors)

        if result_element is None:
            return None

        # 后续 @ 操作
        for op in parts[1:]:
            op = op.strip()
            if not op:
                continue

            if op == "text" or op == "textNodes":
                return result_element.get_text(strip=True)

            # tag.xxx -> 进一步选择
            if op.startswith("tag."):
                tag_name = op[4:]
                result_element = result_element.find(tag_name)
                if result_element is None:
                    return None
                continue

            # 数字索引
            if op.isdigit():
                idx = int(op)
                children = list(result_element.children) if isinstance(result_element, Tag) else []
                if idx < len(children):
                    result_element = children[idx]
                else:
                    return None
                continue

            # 属性名 (src, href, text, etc.)
            if isinstance(result_element, Tag):
                attr = result_element.get(op)
                if attr:
                    return attr

        # 最终如果是 Tag 元素但没有 @ 操作，返回 text
        if isinstance(result_element, Tag):
            return result_element.get_text(strip=True)

        return str(result_element) if result_element else None

    def _css_select(self, soup, selector: str):
        """CSS 选择器查询（支持 class. / id. / tag. 前缀）"""
        selector = selector.strip()
        if selector.startswith("class."):
            return soup.select(f".{selector[6:]}")
        elif selector.startswith("id."):
            return soup.select(f"#{selector[3:]}")
        elif selector.startswith("tag."):
            return soup.select(selector[4:])
        else:
            return soup.select(selector)

    def _css_select_one(self, element, selectors: str):
        """CSS 选择器单步查询（支持链式，如 id.info@tag.p.0@tag.a）"""
        if not selectors or not isinstance(element, Tag):
            return None

        current = element

        if selectors.startswith("id."):
            # id.xxx -> find by id
            id_name = selectors[3:].split("@")[0].split(".")[0]
            current = current.find(id=id_name) if isinstance(current, Tag) else None
        elif selectors.startswith("class."):
            # class.xxx -> find by class
            class_name = selectors[6:].split("@")[0].split(".")[0]
            current = current.find(class_=class_name) if isinstance(current, Tag) else None
        elif selectors.startswith("tag."):
            # tag.xxx -> find by tag name
            tag_name = selectors[4:].split("@")[0].split(".")[0]
            current = current.find(tag_name) if isinstance(current, Tag) else None
        else:
            # 标准 CSS 选择器
            current = current.select_one(selectors)

        return current
