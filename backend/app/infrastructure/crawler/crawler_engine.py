"""
HTTP 爬虫基础设施服务

通用 HTTP 爬虫，支持：
- UA 轮换
- 自动重试
- 代理支持
- HTML / JSON 解析
- 速率限制

作为基础设施层的可复用组件，供各模块调用。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Union
from urllib.parse import urljoin
import time
import random
import logging
import re

logger = logging.getLogger("infra.crawler")


# ============================================================
# 常用 User-Agent 列表
# ============================================================
USER_AGENTS = [
    # Chrome - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Firefox - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Chrome - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Safari - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    # Chrome - Android
    "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    # Mobile Safari - iOS
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


@dataclass
class CrawlResult:
    """爬虫结果"""
    url: str
    success: bool = True
    status_code: int = 200
    html: str = ""
    json_data: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    encoding: str = "utf-8"

    @property
    def text(self) -> str:
        """返回文本内容（html 的别名）"""
        return self.html

    def css_select(self, selector: str) -> List[str]:
        """使用 CSS 选择器提取文本列表（自动检测解析器）"""
        return _css_select_text(self.html, selector)

    def css_select_first(self, selector: str) -> Optional[str]:
        """使用 CSS 选择器提取第一个匹配的文本"""
        results = _css_select_text(self.html, selector)
        return results[0] if results else None

    def xpath(self, xpath_expr: str) -> List[str]:
        """使用 XPath 提取文本列表"""
        return _xpath_text(self.html, xpath_expr)

    def regex(self, pattern: str, group: int = 0) -> List[str]:
        """使用正则表达式提取"""
        try:
            matches = re.findall(pattern, self.html, re.DOTALL)
            if group > 0 and matches and isinstance(matches[0], tuple):
                return [m[group - 1] for m in matches if len(m) >= group]
            return matches
        except re.error:
            return []


def _css_select_text(html: str, selector: str) -> List[str]:
    """CSS 选择器提取文本"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        elements = soup.select(selector)
        return [el.get_text(strip=True) for el in elements if el.get_text(strip=True)]
    except ImportError:
        logger.warning("BeautifulSoup 未安装，CSS 选择器不可用")
        return []


def _xpath_text(html: str, xpath_expr: str) -> List[str]:
    """XPath 提取文本"""
    try:
        from lxml import etree
        tree = etree.HTML(html)
        if tree is None:
            return []
        results = tree.xpath(xpath_expr)
        return [str(r).strip() for r in results if str(r).strip()]
    except ImportError:
        logger.warning("lxml 未安装，XPath 不可用")
        return []


class CrawlerEngine:
    """
    HTTP 爬虫引擎

    特性：
    - UA 轮换
    - 自动重试（指数退避）
    - 代理支持
    - 请求速率限制
    - 编码自动检测

    使用示例:
        crawler = CrawlerEngine()
        result = crawler.get("https://example.com")
        if result.success:
            print(result.text)
    """

    _instance: Optional["CrawlerEngine"] = None

    def __new__(cls, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        rate_limit_per_second: float = 5.0,
        proxy: Optional[str] = None,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        if getattr(self, "_initialized", False):
            return
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.rate_limit_per_second = rate_limit_per_second
        self.proxy = proxy
        self.default_headers = default_headers or {}
        self._last_request_time = 0.0
        self._session = None
        self.user_agents = USER_AGENTS.copy()
        self._initialized = True

    def _get_session(self):
        """获取 requests Session（懒加载）"""
        if self._session is None:
            try:
                import requests
                self._session = requests.Session()
                if self.proxy:
                    self._session.proxies = {
                        "http": self.proxy,
                        "https": self.proxy,
                    }
            except ImportError:
                logger.error("requests 未安装")
                raise
        return self._session

    def _random_ua(self) -> str:
        """随机选择 User-Agent"""
        return random.choice(self.user_agents)

    def _rate_limit(self):
        """速率限制"""
        if self.rate_limit_per_second <= 0:
            return
        min_interval = 1.0 / self.rate_limit_per_second
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        encoding: Optional[str] = None,
        **kwargs,
    ) -> CrawlResult:
        """
        发送 GET 请求

        Args:
            url: 请求 URL
            params: URL 参数
            headers: 自定义请求头
            encoding: 指定编码（默认自动检测）
            **kwargs: 传递给 requests 的其他参数

        Returns:
            CrawlResult
        """
        import time
        start = time.time()

        req_headers = {
            "User-Agent": self._random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            **self.default_headers,
            **(headers or {}),
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                session = self._get_session()
                response = session.get(
                    url,
                    params=params,
                    headers=req_headers,
                    timeout=self.timeout,
                    **kwargs,
                )

                if encoding:
                    response.encoding = encoding
                elif not response.encoding or response.encoding == "ISO-8859-1":
                    response.encoding = response.apparent_encoding or "utf-8"

                elapsed = (time.time() - start) * 1000
                json_data = None
                if "application/json" in response.headers.get("content-type", ""):
                    try:
                        json_data = response.json()
                    except Exception:
                        pass

                return CrawlResult(
                    url=response.url,
                    success=True,
                    status_code=response.status_code,
                    html=response.text,
                    json_data=json_data,
                    headers=dict(response.headers),
                    elapsed_ms=elapsed,
                    encoding=response.encoding or "utf-8",
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"[Crawler] 请求失败 (attempt {attempt + 1}/{self.max_retries}): {url} - {e}"
                )
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)

        elapsed = (time.time() - start) * 1000
        return CrawlResult(
            url=url,
            success=False,
            status_code=0,
            error=last_error,
            elapsed_ms=elapsed,
        )

    def post(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        encoding: Optional[str] = None,
        **kwargs,
    ) -> CrawlResult:
        """发送 POST 请求"""
        import time
        start = time.time()

        req_headers = {
            "User-Agent": self._random_ua(),
            "Accept": "application/json,text/html,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            **self.default_headers,
            **(headers or {}),
        }

        try:
            self._rate_limit()
            session = self._get_session()
            response = session.post(
                url,
                data=data,
                json=json,
                headers=req_headers,
                timeout=self.timeout,
                **kwargs,
            )

            if encoding:
                response.encoding = encoding
            elif not response.encoding or response.encoding == "ISO-8859-1":
                response.encoding = response.apparent_encoding or "utf-8"

            elapsed = (time.time() - start) * 1000
            json_data = None
            if "application/json" in response.headers.get("content-type", ""):
                try:
                    json_data = response.json()
                except Exception:
                    pass

            return CrawlResult(
                url=response.url,
                success=True,
                status_code=response.status_code,
                html=response.text,
                json_data=json_data,
                headers=dict(response.headers),
                elapsed_ms=elapsed,
                encoding=response.encoding or "utf-8",
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return CrawlResult(
                url=url,
                success=False,
                status_code=0,
                error=str(e),
                elapsed_ms=elapsed,
            )

    def batch_get(self, urls: List[str], **kwargs) -> List[CrawlResult]:
        """批量 GET 请求"""
        return [self.get(url, **kwargs) for url in urls]
