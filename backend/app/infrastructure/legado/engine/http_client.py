"""
异步 HTTP 请求引擎

基于 aiohttp，专为 Legado 书源抓取优化：
- 支持 GET / POST
- 自动编码检测
- Cookie 管理
- 重定向处理
- 超时与重试
- 并发控制
- SSL 验证开关
"""

import asyncio
import ipaddress
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

import aiohttp
from aiohttp import CookieJar
import logging

logger = logging.getLogger("legado_http")


@dataclass
class HttpResponse:
    """HTTP 响应封装"""
    url: str
    status: int
    headers: Dict[str, str] = field(default_factory=dict)
    text: str = ""
    content: bytes = b""
    json_data: Any = None
    is_json: bool = False
    is_html: bool = False
    elapsed_ms: int = 0
    error: Optional[str] = None
    charset: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and 200 <= self.status < 400

    @property
    def html(self) -> str:
        return self.text


class LegadoHttpClient:
    """
    Legado 专用 HTTP 客户端

    特性：
    - 自动编码检测（中文站点优先 GBK/UTF-8
    - Cookie 持久化
    - 自动重试（指数退避）
    - User-Agent 轮换
    - SSL 验证可选（默认关闭，因为很多书源证书过期）
    - 连接池管理
    """

    DEFAULT_UAS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    ]

    DEFAULT_HEADERS = {
        "Accept": "application/json, text/html, application/xhtml+xml, text/plain, */*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        # aiohttp only decodes Brotli when an optional Brotli package is installed.
        # Do not advertise `br` in the baseline transport, otherwise ordinary
        # source probes fail before rule parsing with a decoder exception.
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    def __init__(
        self,
        timeout: int = 15,
        max_retries: int = 2,
        verify_ssl: bool = False,
        max_concurrent: int = 10,
        user_agent: str = None,
    ):
        self._timeout = timeout
        self._max_retries = max_retries
        self._verify_ssl = verify_ssl
        self._max_concurrent = max_concurrent
        self._user_agent = user_agent or self.DEFAULT_UAS[0]
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._cookie_jar: Optional[CookieJar] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取（或创建）aiohttp session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            connector = aiohttp.TCPConnector(
                limit=self._max_concurrent,
                ssl=self._verify_ssl,
                force_close=False,
                enable_cleanup_closed=True,
            )
            if self._cookie_jar is None:
                self._cookie_jar = CookieJar(unsafe=True)  # unsafe=True 允许 IP 地址的 cookie
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                cookie_jar=self._cookie_jar,
                trust_env=True,
                headers={
                    "User-Agent": self._user_agent,
                    **self.DEFAULT_HEADERS,
                },
            )
        return self._session

    async def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    async def get(
        self,
        url: str,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        encoding: str = None,
        **kwargs,
    ) -> HttpResponse:
        """发送 GET 请求"""
        return await self._request("GET", url, params=params, headers=headers, encoding=encoding, **kwargs)

    async def post(
        self,
        url: str,
        data: Any = None,
        json_data: Any = None,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        encoding: str = None,
        **kwargs,
    ) -> HttpResponse:
        """发送 POST 请求"""
        return await self._request(
            "POST", url,
            data=data,
            json_data=json_data,
            params=params,
            headers=headers,
            encoding=encoding,
            **kwargs,
        )

    async def head(
        self,
        url: str,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        encoding: str = None,
        **kwargs,
    ) -> HttpResponse:
        """Send a HEAD request while retaining the normal response metadata."""
        return await self._request("HEAD", url, params=params, headers=headers, encoding=encoding, **kwargs)

    async def _request(
        self,
        method: str,
        url: str,
        params: Dict[str, Any] = None,
        data: Any = None,
        json_data: Any = None,
        headers: Dict[str, str] = None,
        encoding: str = None,
        **kwargs,
    ) -> HttpResponse:
        """执行 HTTP 请求（带重试）"""
        sem = await self._get_semaphore()
        async with sem:
            last_error = None
            for attempt in range(self._max_retries + 1):
                try:
                    return await self._do_request(
                        method, url,
                        params=params,
                        data=data,
                        json_data=json_data,
                        headers=headers,
                        encoding=encoding,
                        **kwargs,
                    )
                except Exception as e:
                    last_error = e
                    if attempt < self._max_retries:
                        wait = 0.5 * (2 ** attempt)  # 指数退避
                        await asyncio.sleep(wait)
                    continue

            # 所有重试都失败
            return HttpResponse(
                url=url,
                status=0,
                error=str(last_error) if last_error else "Unknown error",
            )

    async def _do_request(
        self,
        method: str,
        url: str,
        params: Dict[str, Any] = None,
        data: Any = None,
        json_data: Any = None,
        headers: Dict[str, str] = None,
        encoding: str = None,
        dns_ip: str = None,
        **kwargs,
    ) -> HttpResponse:
        """执行单次请求"""
        start = time.time()
        session = await self._get_session()

        req_headers = {}
        if headers:
            req_headers.update(headers)

        request_url = url
        if dns_ip and self._is_ip_address(dns_ip):
            parsed = urlparse(url)
            if parsed.hostname:
                port = parsed.port
                replacement = f"[{dns_ip}]" if ":" in dns_ip else dns_ip
                if port:
                    replacement = f"{replacement}:{port}"
                request_url = urlunparse(parsed._replace(netloc=replacement))
                if not any(key.lower() == "host" for key in req_headers):
                    original_host = parsed.hostname
                    if port:
                        original_host = f"{original_host}:{port}"
                    req_headers["Host"] = original_host

        kwargs_final = {}
        if params:
            kwargs_final["params"] = params
        if data is not None:
            kwargs_final["data"] = data
        if json_data is not None:
            kwargs_final["json"] = json_data
        if req_headers:
            kwargs_final["headers"] = req_headers

        # 透传其他参数
        for k, v in kwargs.items():
            if k not in kwargs_final:
                kwargs_final[k] = v

        async with session.request(method, request_url, **kwargs_final) as resp:
            content = await resp.read()
            elapsed = int((time.time() - start) * 1000)

            # 检测编码
            text = self._decode_content(content, resp, encoding)

            # 解析 JSON
            json_data_parsed = None
            is_json = False
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type or "json" in content_type.lower():
                try:
                    json_data_parsed = json.loads(text)
                    is_json = True
                except (json.JSONDecodeError, ValueError):
                    pass

            # 判断是否 HTML
            is_html = "text/html" in content_type or (
                text.strip().startswith("<") and text.strip().endswith(">")
            )

            # 响应头
            resp_headers = {k: v for k, v in resp.headers.items()}

            return HttpResponse(
                url=url if request_url != url else str(resp.url),
                status=resp.status,
                headers=resp_headers,
                text=text,
                content=content,
                charset=getattr(resp, "charset", None),
                json_data=json_data_parsed,
                is_json=is_json,
                is_html=is_html,
                elapsed_ms=elapsed,
            )

    @staticmethod
    def _decode_content(content: bytes, resp: aiohttp.ClientResponse, encoding: str = None) -> str:
        """
        智能解码响应内容

        优先使用指定编码，然后尝试 Content-Type 中的编码，
        再尝试 UTF-8，最后 GBK（中文站点常见）
        """
        if not content:
            return ""

        # 1. 指定编码
        if encoding:
            try:
                return content.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                pass

        # 2. Content-Type 中的 charset
        content_type = resp.headers.get("Content-Type", "")
        charset_match = re.search(r'charset=([\w-]+)', content_type, re.IGNORECASE)
        if charset_match:
            charset = charset_match.group(1)
            try:
                return content.decode(charset)
            except (UnicodeDecodeError, LookupError):
                pass

        # 3. 尝试 UTF-8
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            pass

        # 4. 尝试 GBK（中文小说站常用）
        try:
            return content.decode("gbk")
        except UnicodeDecodeError:
            pass

        # 5. 尝试 GB18030
        try:
            return content.decode("gb18030")
        except UnicodeDecodeError:
            pass

        # 6. 最后用 utf-8 替换错误
        return content.decode("utf-8", errors="replace")

    @staticmethod
    def _is_ip_address(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    async def close(self):
        """关闭 session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ==================== Cookie 管理 ====================

    def get_cookies(self, url: str) -> Dict[str, str]:
        """获取指定 URL 的 cookies"""
        try:
            parsed = urlparse(url)
            cookies = {}
            for cookie in self._cookie_jar:
                # 简单匹配域名
                if cookie["domain"] in parsed.netloc or parsed.netloc in cookie["domain"]:
                    cookies[cookie.key] = cookie.value
            return cookies
        except Exception:
            return {}

    def set_cookie(self, domain: str, name: str, value: str):
        """设置 cookie"""
        # aiohttp 的 CookieJar 比较难直接操作
        # 这里简化处理
        pass

    # ==================== 工具方法 ====================

    def random_ua(self) -> str:
        """随机获取一个 User-Agent"""
        import random
        return random.choice(self.DEFAULT_UAS)

    def set_user_agent(self, ua: str):
        """设置 User-Agent"""
        self._user_agent = ua
