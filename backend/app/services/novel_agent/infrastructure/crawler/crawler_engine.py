"""
爬虫基础设施 - Crawler Engine

底层 HTTP 请求、解析、反爬能力。
上层书源技能通过统一接口调用。

设计原则（参考 OpenClaw）：
- 能力下沉：通用爬虫逻辑不属于特定技能
- 可复用：书源查找、章节采集都依赖它
- 多策略：直连 / 代理 / 无头浏览器
- 反爬：UA 轮换、请求频率控制、重试
"""

from __future__ import annotations

import re
import time
import random
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


@dataclass
class CrawlResult:
    url: str
    status: int = 0
    html: str = ""
    title: str = ""
    text: str = ""
    links: List[str] = field(default_factory=list)
    error: str = ""
    elapsed: float = 0.0

    @property
    def success(self) -> bool:
        return self.status == 200 and not self.error


class CrawlerEngine:
    """爬虫引擎 - 底层基础设施

    能力：
    - HTTP 请求（同步/异步）
    - HTML 解析（BeautifulSoup）
    - 链接提取
    - UA 轮换
    - 请求频率控制
    - 自动重试
    """

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        delay_range: Tuple[float, float] = (0.5, 2.0),
        use_proxy: bool = False,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.delay_range = delay_range
        self.use_proxy = use_proxy
        self._session = None

    def _get_headers(self, referer: str = "") -> Dict[str, str]:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    def fetch(self, url: str, method: str = "GET", referer: str = "", **kwargs) -> CrawlResult:
        """同步抓取页面"""
        result = CrawlResult(url=url)
        start = time.time()

        if not HAS_HTTPX:
            result.error = "httpx not installed. Install with: pip install httpx"
            return result

        for attempt in range(self.max_retries):
            try:
                if self._session is None:
                    self._session = httpx.Client(
                        timeout=self.timeout,
                        follow_redirects=True,
                    )

                response = self._session.request(
                    method,
                    url,
                    headers=self._get_headers(referer),
                    **kwargs,
                )

                result.status = response.status_code
                result.html = response.text
                result.elapsed = time.time() - start

                if result.status == 200:
                    result.title = self._extract_title(result.html)
                    result.text = self._extract_text(result.html)
                    result.links = self._extract_links(result.html, url)
                else:
                    result.error = f"HTTP {result.status}"

                break

            except Exception as e:
                result.error = str(e)
                if attempt < self.max_retries - 1:
                    time.sleep(random.uniform(*self.delay_range) * (attempt + 1))
                continue

        return result

    def search(self, keyword: str, search_url: str = "", **kwargs) -> List[Dict[str, str]]:
        """搜索关键词（使用搜索引擎或站点搜索）

        返回: [{"title": "...", "url": "...", "snippet": "..."}, ...]
        """
        if not search_url:
            search_url = f"https://www.bing.com/search?q={keyword}"

        result = self.fetch(search_url.format(q=keyword), **kwargs)
        if not result.success:
            return []

        return self._parse_search_results(result.html, result.url)

    def _extract_title(self, html: str) -> str:
        if not HAS_BS4:
            match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            return match.group(1).strip() if match else ""
        try:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string:
                return soup.title.string.strip()
        except Exception:
            pass
        return ""

    def _extract_text(self, html: str) -> str:
        if not HAS_BS4:
            text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"\s+", " ", text)
            return text.strip()
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)
        except Exception:
            return ""

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        if not HAS_BS4:
            links = re.findall(r'href=["\'](https?://[^"\']+)["\']', html)
            return list(set(links))[:50]
        try:
            soup = BeautifulSoup(html, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http"):
                    links.append(href)
                elif href.startswith("/"):
                    parsed = urlparse(base_url)
                    links.append(urljoin(f"{parsed.scheme}://{parsed.netloc}", href))
            return list(set(links))[:50]
        except Exception:
            return []

    def _parse_search_results(self, html: str, base_url: str) -> List[Dict[str, str]]:
        if not HAS_BS4:
            return []
        results = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            for item in soup.select(".b_algo, .g, .result"):
                title_tag = item.select_one("h2, h3, .title")
                link_tag = item.select_one("a[href]")
                snippet_tag = item.select_one(".b_caption p, .st, .snippet")
                if link_tag and link_tag.get("href", "").startswith("http"):
                    results.append({
                        "title": title_tag.get_text(strip=True) if title_tag else "",
                        "url": link_tag["href"],
                        "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
                    })
        except Exception:
            pass
        return results[:20]

    def close(self):
        if self._session:
            self._session.close()
            self._session = None


_crawler_singleton: Optional[CrawlerEngine] = None


def crawler_engine(**kwargs) -> CrawlerEngine:
    """获取爬虫引擎单例"""
    global _crawler_singleton
    if _crawler_singleton is None:
        _crawler_singleton = CrawlerEngine(**kwargs)
    return _crawler_singleton
