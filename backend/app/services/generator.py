"""
写源引擎 - 根据 URL 自动分析页面结构，生成 Legado 书源/订阅源

职责：
- 页面拉取与解析
- RSS/Atom/HTML 结构检测
- 规则自动推断
- 兼容性兜底
- 全链路日志
"""

import time
import re
import json
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from ..core.logging import get_logger
from ..core.exceptions import ValidationException, ExternalServiceException
from ..core.compatibility import compat_engine

logger = get_logger("engine.generator")


class SourceGenerator:
    """自动写源引擎"""

    def __init__(self):
        self.logs: List[str] = []

    def _log(self, msg: str, level: str = "info"):
        """统一日志：同时记录到 logs 列表和统一日志系统"""
        self.logs.append(msg)
        log_func = getattr(logger, level, logger.info)
        log_func(f"[Generator] {msg}", extra={"action": "generate"})

    async def generate(self, url: str, source_type: str = "rss", source_name: Optional[str] = None) -> Dict[str, Any]:
        """
        主入口：根据 URL 生成源

        异常处理：
        - URL 校验失败 -> ValidationException
        - 网络请求失败 -> ExternalServiceException
        - 解析失败 -> 返回 failure + 兜底方案
        """
        self.logs = []
        self._log(f"开始分析 URL: {url}")

        if not url or not url.startswith(("http://", "https://")):
            self._log(f"URL 格式错误: {url}", "warning")
            raise ValidationException("URL 必须以 http:// 或 https:// 开头")

        # 1. 拉取页面
        html, content_type = await self._fetch_page(url)
        if not html:
            self._log("页面拉取失败，使用兼容性兜底", "warning")
            fallback = compat_engine.generate_from_url(url, source_name)
            score = compat_engine.get_compatibility_score(fallback)
            return {
                "success": score.get("is_usable", False),
                "source": fallback,
                "message": "页面拉取失败，使用兼容性规则兜底",
                "logs": self.logs,
            }

        # 2. 检测内容类型并生成
        try:
            if "xml" in content_type or html.strip().startswith(("<?xml", "<feed", "<rss")):
                self._log("检测到 RSS/Atom Feed")
                source = await self._generate_rss_source(url, html, source_name)
            elif source_type == "book":
                self._log("尝试生成书源")
                source = await self._generate_book_source(url, html, source_name)
            else:
                self._log("尝试生成订阅源")
                source = await self._generate_rss_source_from_html(url, html, source_name)
        except Exception as e:
            self._log(f"源生成异常: {type(e).__name__}: {e}", "error")
            logger.error(
                f"[Generator] 源生成异常: {url} - {type(e).__name__}: {e}",
                extra={"action": "generate", "source_url": url, "error": str(e)},
                exc_info=True
            )
            source = None

        # 3. 兜底处理
        if not source:
            self._log("自动解析失败，使用兼容性规则兜底", "warning")
            source = compat_engine.generate_from_url(url, source_name)

        # 4. 评分与修复
        score_info = compat_engine.get_compatibility_score(source)
        self._log(f"兼容性评分: {score_info['grade']} ({score_info['score']}/100)")

        repaired = compat_engine.repair_source(source)
        fixes = repaired.pop("_fixes", [])
        if fixes:
            self._log(f"自动修复 {len(fixes)} 个问题: {', '.join(fixes)}")
            source = repaired

        return {
            "success": score_info.get("is_usable", False),
            "source": source,
            "message": "生成成功",
            "logs": self.logs,
            "compatibility": score_info,
        }

    async def _fetch_page(self, url: str) -> tuple[Optional[str], str]:
        """拉取页面，返回 (html, content_type)"""
        start = time.time()
        try:
            timeout = aiohttp.ClientTimeout(total=20, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, ssl=False) as resp:
                    elapsed = (time.time() - start) * 1000
                    html = await resp.text(errors="replace")
                    content_type = resp.headers.get("Content-Type", "").lower()

                    self._log(f"页面拉取成功: HTTP {resp.status}, {elapsed:.0f}ms, Content-Type: {content_type}")

                    if resp.status >= 400:
                        logger.warning(
                            f"[Generator] 页面返回错误: {url} HTTP {resp.status}",
                            extra={"action": "fetch_page", "source_url": url, "status_code": resp.status, "duration_ms": round(elapsed, 2)}
                        )
                        return None, content_type

                    return html, content_type

        except asyncio.TimeoutError:
            elapsed = (time.time() - start) * 1000
            self._log(f"页面拉取超时: {elapsed:.0f}ms", "error")
            logger.error(
                f"[Generator] 页面拉取超时: {url}",
                extra={"action": "fetch_page", "source_url": url, "error": "timeout", "duration_ms": round(elapsed, 2)}
            )
            return None, ""
        except aiohttp.ClientError as e:
            self._log(f"连接失败: {type(e).__name__}: {e}", "error")
            logger.error(
                f"[Generator] 连接失败: {url} - {e}",
                extra={"action": "fetch_page", "source_url": url, "error": str(e)}
            )
            return None, ""
        except Exception as e:
            self._log(f"未知错误: {type(e).__name__}: {e}", "error")
            logger.error(
                f"[Generator] 拉取异常: {url} - {e}",
                extra={"action": "fetch_page", "source_url": url, "error": str(e)},
                exc_info=True
            )
            return None, ""

    async def _generate_rss_source(self, url: str, xml: str, source_name: Optional[str]) -> Optional[Dict]:
        """从 RSS/Atom XML 生成订阅源"""
        import feedparser
        feed = feedparser.parse(xml)
        name = source_name or feed.feed.get("title", "自动识别 RSS")

        self._log(f"Feed 标题: {name}")
        self._log(f"条目数: {len(feed.entries)}")

        soup = BeautifulSoup(xml, "xml")
        entries = soup.find_all(["item", "entry"])
        if not entries:
            self._log("未找到任何 entry/item", "warning")

        # 构建规则
        if soup.find("entry"):
            rule_articles, rule_title, rule_link = "entry", "title", "link@href"
            rule_pub_date, rule_desc, rule_content = "published||updated", "summary||subtitle", "content"
        elif soup.find("item"):
            rule_articles, rule_title, rule_link = "item", "title", "link"
            rule_pub_date, rule_desc, rule_content = "pubDate", "description", "description"
        else:
            self._log("未识别标准 RSS/Atom 结构，使用通用规则", "warning")
            rule_articles, rule_title, rule_link = "item,entry", "title", "link"
            rule_pub_date, rule_desc, rule_content = "pubDate,published", "description,summary", "description"

        self._log(f"规则构建完成: articles={rule_articles}, title={rule_title}, link={rule_link}")

        return {
            "sourceUrl": url,
            "sourceName": name,
            "sourceGroup": "自动生成",
            "sourceComment": f"由 LegadoHub 写源引擎生成\n原始URL: {url}",
            "enabled": True,
            "ruleArticles": rule_articles,
            "ruleTitle": rule_title,
            "ruleLink": rule_link,
            "rulePubDate": rule_pub_date,
            "ruleDescription": rule_desc,
            "ruleContent": rule_content,
            "ruleImage": "",
            "type": 0,
            "singleUrl": False,
        }

    async def _generate_rss_source_from_html(self, url: str, html: str, source_name: Optional[str]) -> Optional[Dict]:
        """从 HTML 页面生成订阅源"""
        soup = BeautifulSoup(html, "lxml")

        # 检测 RSS/Atom 链接
        for link_type, tag in [("RSS", "application/rss+xml"), ("Atom", "application/atom+xml")]:
            links = soup.find_all("link", type=tag)
            if links:
                href = links[0].get("href")
                if href:
                    full_url = urljoin(url, href)
                    self._log(f"发现 {link_type} 链接: {full_url}")
                    return await self.generate(full_url, "rss", source_name)

        # 无 RSS，尝试分析 HTML
        name = source_name or self._extract_title(soup)
        self._log(f"页面标题: {name}")

        article_selectors = self._detect_article_list(soup)
        if not article_selectors:
            self._log("未能自动识别文章列表结构", "warning")
            return None

        articles_sel, title_sel, link_sel, desc_sel, img_sel, date_sel = article_selectors
        self._log(f"检测到列表结构: {articles_sel}")

        return {
            "sourceUrl": url,
            "sourceName": name,
            "sourceGroup": "自动生成",
            "sourceComment": f"由 LegadoHub 从 HTML 分析生成\n原始URL: {url}",
            "enabled": True,
            "ruleArticles": articles_sel,
            "ruleTitle": title_sel,
            "ruleLink": link_sel,
            "rulePubDate": date_sel,
            "ruleDescription": desc_sel,
            "ruleImage": img_sel,
            "ruleContent": "",
            "type": 0,
            "singleUrl": False,
        }

    async def _generate_book_source(self, url: str, html: str, source_name: Optional[str]) -> Optional[Dict]:
        """从小说网站生成书源"""
        soup = BeautifulSoup(html, "lxml")
        name = source_name or self._extract_title(soup)
        self._log(f"页面标题: {name}")

        # 检测搜索框
        search_url = ""
        search_form = soup.find("form")
        if search_form:
            action = search_form.get("action", "")
            for inp in search_form.find_all("input"):
                if inp.get("type") == "text" or inp.get("name") in ("q", "search", "keyword", "key", "kw"):
                    search_url = f"{urljoin(url, action)}?{{'searchKey': 'searchKey'}}"
                    self._log(f"推测搜索接口: {search_url}")
                    break

        toc = self._detect_toc_structure(soup)

        source = {
            "bookSourceUrl": url,
            "bookSourceName": name,
            "bookSourceGroup": "自动生成",
            "bookSourceComment": f"由 LegadoHub 写源引擎生成\n原始URL: {url}\n注意：规则需手动调整",
            "enabled": False,
            "searchUrl": search_url,
            "ruleSearch": {"bookList": "", "name": "", "author": "", "bookUrl": ""},
            "ruleBookInfo": {"name": "", "author": "", "intro": "", "coverUrl": "", "tocUrl": ""},
            "ruleToc": toc,
            "ruleContent": {"content": ""},
        }

        self._log("书源模板生成完成")
        return source

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """安全提取页面标题"""
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return "自动生成"

    def _detect_article_list(self, soup: BeautifulSoup) -> Optional[tuple]:
        """检测 HTML 中的文章列表结构"""
        candidates = [
            ("article", "h2 a", "h2 a@href", "p", "img@src", "time"),
            (".post", ".entry-title a", ".entry-title a@href", ".entry-summary", "img@src", ".published"),
            (".item", ".title a", ".title a@href", ".desc", "img@src", ".date"),
            ("li", "a", "a@href", "span", "img@src", ".time"),
            (".news-item", ".news-title", ".news-title a@href", ".news-summary", "img@src", ".news-date"),
        ]

        for sel in candidates:
            try:
                elements = soup.select(sel[0]) if "." in sel[0] or "#" in sel[0] else soup.find_all(sel[0])
                if len(elements) >= 2:
                    self._log(f"检测到列表: {sel[0]}, {len(elements)} 项")
                    return sel
            except Exception:
                continue

        # 兜底：找链接密集容器
        for container in soup.find_all(["ul", "ol", "div"]):
            links = container.find_all("a", href=True)
            if len(links) >= 3:
                self._log(f"链接密度检测: {container.name}")
                return (container.name, "a", "a@href", "", "", "")

        return None

    def _detect_toc_structure(self, soup: BeautifulSoup) -> Dict[str, str]:
        """检测小说目录结构"""
        result = {"chapterList": "", "chapterName": "", "chapterUrl": ""}
        candidates = ["div#list dd a", ".catalog-list a", "#catalog li a", ".chapter-item a", "dl dd a"]

        for selector in candidates:
            try:
                elements = soup.select(selector)
                if len(elements) >= 5:
                    self._log(f"检测到目录: {selector}, {len(elements)} 章")
                    result["chapterList"] = selector
                    result["chapterName"] = "text"
                    result["chapterUrl"] = "href"
                    return result
            except Exception:
                continue

        self._log("未检测到目录结构", "warning")
        return result
