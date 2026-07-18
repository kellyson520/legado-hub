"""
Legado 书源抓取器。

当前版本保持既有 search/toc/content/book_info 行为，并新增：
- 纯 `@js:` searchUrl 执行
- 统一 stage/context 传递给 JsRuntime
"""

from __future__ import annotations

import json
import inspect
import logging
import re
from typing import Any, Dict, List
from urllib.parse import quote

from .engine import (
    HttpResponse,
    JsonPathExt,
    JsRuntime,
    LegadoHttpClient,
    LegadoRuntimeFacade,
    RuleSelector,
    TextPipeline,
    UrlUtils,
)
from .engine.runtime_bridge import RuntimeBridge

logger = logging.getLogger("legado_fetcher")


class LegadoBookSourceFetcher:
    def __init__(
        self,
        timeout: int = 15,
        max_retries: int = 2,
        verify_ssl: bool = False,
        max_concurrent: int = 10,
        http_client=None,
        runtime_facade=None,
    ):
        self._http = http_client or LegadoHttpClient(
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            max_concurrent=max_concurrent,
        )
        self._js_runtime = JsRuntime()
        self._runtime_facade = runtime_facade or LegadoRuntimeFacade(
            bridge_handler=RuntimeBridge(http_client=self._http).handle,
        )

    def set_execution_deadline(self, deadline: float | None) -> None:
        setter = getattr(self._js_runtime, 'set_execution_deadline', None)
        if callable(setter):
            setter(deadline)

    def _selector_context(self, **kwargs) -> Dict[str, Any]:
        return {
            "js_runtime": self._js_runtime,
            "runtime_facade": self._runtime_facade,
            "cache": getattr(self._js_runtime, "_cache", {}),
            **kwargs,
        }

    async def search(
        self,
        source: Dict[str, Any],
        keyword: str,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        search_url_tmpl = source.get("searchUrl", "")
        if not search_url_tmpl:
            return []

        rule_search = self._parse_rule(source.get("ruleSearch", {}))
        if not rule_search:
            return []

        base_url = UrlUtils.get_base_url(source.get("bookSourceUrl", ""))
        parse_base_url = base_url if UrlUtils.is_valid_url(base_url) else ""
        url_tmpl, method, body_tmpl = UrlUtils.parse_search_url(search_url_tmpl)
        url_config = UrlUtils.parse_url_config(search_url_tmpl)
        charset = url_config.get("charset", "")

        encoded_keyword = keyword
        if charset and charset.lower() in ("gbk", "gb2312", "gb18030"):
            try:
                encoded_keyword = keyword.encode(charset).decode("latin-1")
            except (UnicodeEncodeError, LookupError):
                encoded_keyword = quote(keyword.encode("utf-8"))
        else:
            encoded_keyword = quote(keyword)

        variables = {
            "keyword": keyword,
            "key": encoded_keyword,
            "searchKey": encoded_keyword,
            "searchkey": encoded_keyword,
            "page": page,
            "start": (page - 1) * 20,
            "limit": 20,
            "size": 20,
            "pageSize": 20,
        }
        headers = UrlUtils.parse_headers(source.get("header", ""))
        is_js_search = search_url_tmpl.strip().startswith("@js:")
        js_search_code = search_url_tmpl.strip()[4:].strip() if is_js_search else ""

        # Some native Legado rules use the first character of `key` as an
        # explicit mode prefix (`@`, `#`, `%`). Percent-encoding a normal
        # Chinese keyword makes every query look like `%...` and routes it to
        # the wrong endpoint. Keep these prefix-sensitive rules on raw input.
        if is_js_search and self.js_search_prefers_raw_key(js_search_code):
            variables.update(
                {
                    "key": keyword,
                    "searchKey": keyword,
                    "searchkey": keyword,
                }
            )

        resp_data: Any = None
        response_is_html = False

        if is_js_search:
            output = self._js_runtime.execute_with_metadata(
                js_search_code,
                data=None,
                stage="search_url_js",
                source=source,
                baseUrl=base_url,
                variables=variables,
                headers=headers,
            )
            if not output.success:
                return []

            request_spec, response_payload = self._coerce_js_search_output(
                output.value,
                base_url=base_url,
            )

            if request_spec:
                request_url = request_spec.get("url", "")
                if request_url and not request_url.startswith("http"):
                    request_url = UrlUtils.resolve_relative(request_url, base_url)
                parse_base_url = request_url or parse_base_url
                request_method = str(request_spec.get("method", "GET")).upper()
                request_headers = {**headers, **(request_spec.get("headers") or {})}
                if request_method == "POST":
                    request_body = request_spec.get("body")
                    if isinstance(request_body, dict):
                        resp = await self._http.post(request_url, json_data=request_body, headers=request_headers)
                    else:
                        resp = await self._http.post(request_url, data=request_body, headers=request_headers)
                else:
                    resp = await self._http.get(request_url, headers=request_headers)
                if not resp.success:
                    return []
                resp_data = self._extract_response_data(resp)
                response_is_html = resp.is_html
            else:
                resp_data = response_payload
                response_is_html = isinstance(resp_data, str)
        else:
            search_url = UrlUtils.fill_template(url_tmpl, variables, encode=False)
            if not search_url.startswith("http"):
                search_url = UrlUtils.resolve_relative(search_url, base_url)
            parse_base_url = search_url or parse_base_url

            body_data = None
            if method == "POST" and body_tmpl:
                body_str = UrlUtils.fill_template(body_tmpl, variables, encode=False)
                if body_str.startswith("{") or body_str.startswith("["):
                    try:
                        body_data = json.loads(body_str)
                    except json.JSONDecodeError:
                        body_data = body_str
                else:
                    body_data = body_str

            try:
                if method == "POST":
                    if isinstance(body_data, dict):
                        resp = await self._http.post(search_url, json_data=body_data, headers=headers)
                    else:
                        resp = await self._http.post(search_url, data=body_data, headers=headers)
                else:
                    resp = await self._http.get(search_url, headers=headers)
            except Exception as e:
                logger.debug(f"search request failed {source.get('bookSourceName', '')}: {e}")
                return []

            if not resp.success:
                return []

            resp_data = self._extract_response_data(resp)
            response_is_html = resp.is_html

        book_list_rule = rule_search.get("bookList", "")
        if not book_list_rule:
            return []

        extraction_base_url = parse_base_url or base_url
        book_list = self._extract_list(
            resp_data,
            book_list_rule,
            response_is_html,
            extraction_base_url,
            stage="search",
        )
        if not book_list:
            return []

        field_map = {
            "name": rule_search.get("name") or rule_search.get("bookName") or "",
            "author": rule_search.get("author", ""),
            "bookUrl": rule_search.get("bookUrl") or rule_search.get("resultUrl") or "",
            "coverUrl": rule_search.get("coverUrl") or rule_search.get("cover") or "",
            "intro": rule_search.get("intro") or rule_search.get("note") or "",
            "lastChapter": rule_search.get("lastChapter", ""),
            "kind": rule_search.get("kind", ""),
            "wordCount": rule_search.get("wordCount", ""),
            "lastUpdate": rule_search.get("lastUpdate", ""),
        }

        results: list[dict[str, Any]] = []
        for item in book_list:
            book_info = {
                "sourceName": source.get("bookSourceName", ""),
                "sourceUrl": source.get("bookSourceUrl", ""),
                "_source_config": source,
            }

            for field, rule in field_map.items():
                if not rule:
                    continue
                value = self._extract_field(
                    item,
                    rule,
                    extraction_base_url,
                    response_is_html,
                    field,
                    stage="search",
                )
                book_info[field] = value

            if book_info.get("bookUrl") and not book_info["bookUrl"].startswith("http"):
                book_info["bookUrl"] = UrlUtils.resolve_relative(book_info["bookUrl"], extraction_base_url)
            if book_info.get("coverUrl") and not book_info["coverUrl"].startswith("http"):
                book_info["coverUrl"] = UrlUtils.resolve_relative(book_info["coverUrl"], extraction_base_url)

            if book_info.get("name") and book_info.get("bookUrl"):
                results.append(book_info)

        return results

    @staticmethod
    def _coerce_js_search_output(value: Any, base_url: str) -> tuple[dict[str, Any] | None, Any]:
        if isinstance(value, dict):
            request_spec = value.get("request")
            response_payload = value.get("response")
            return request_spec, response_payload

        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("/"):
                if ",{" in raw:
                    url, option_text = raw.split(",", 1)
                    try:
                        option = json.loads(option_text)
                        return {
                            "url": url,
                            "method": str(option.get("method", "GET")).upper(),
                            "body": option.get("body"),
                            "headers": option.get("headers") or {},
                        }, None
                    except json.JSONDecodeError:
                        return {"url": raw, "method": "GET", "headers": {}}, None
                return {"url": raw, "method": "GET", "headers": {}}, None

            if raw.startswith("./") or raw.startswith("../"):
                return {"url": UrlUtils.resolve_relative(raw, base_url), "method": "GET", "headers": {}}, None

        return None, value

    @staticmethod
    def js_search_prefers_raw_key(code: str) -> bool:
        return bool(
            re.search(
                r"\bkey\.(?:charAt|slice|startsWith|startsWith|substring)\s*\(",
                code or "",
            )
        )

    async def get_toc(
        self,
        source: Dict[str, Any],
        book_url: str,
    ) -> List[Dict[str, Any]]:
        rule_toc = self._parse_rule(source.get("ruleToc", {}))
        if not rule_toc:
            return []

        base_url = UrlUtils.get_base_url(source.get("bookSourceUrl", ""))
        headers = UrlUtils.parse_headers(source.get("header", ""))

        rule_book_info = self._parse_rule(source.get("ruleBookInfo", {}))
        toc_url_rule = rule_book_info.get("tocUrl", "")

        toc_url = ""
        detail_data = None
        detail_base_url = base_url
        if toc_url_rule:
            try:
                detail_resp, detail_base_url = await self._request_configured_url(
                    book_url,
                    headers=headers,
                    base_url=base_url,
                )
            except Exception as e:
                logger.debug(f"detail request failed {source.get('bookSourceName', '')}: {e}")
                return []

            if not detail_resp.success:
                return []

            detail_data = self._extract_response_data(detail_resp)
            init_rule = rule_book_info.get("init", "")
            if init_rule and isinstance(detail_data, dict):
                init_result = self._runtime_facade.extract(
                    detail_data,
                    init_rule,
                    operation="extract_string",
                    stage="book_info_init",
                    base_url=detail_base_url,
                    context=self._selector_context(source=source, stage="book_info_init"),
                )
                if init_result.success and init_result.value is not None:
                    detail_data = init_result.value

            if "{{" in toc_url_rule and "}}" in toc_url_rule:
                extra_vars = {"baseUrl": book_url}
                if isinstance(detail_data, dict):
                    result_vars = dict(detail_data)
                    if "data" in detail_data and isinstance(detail_data["data"], dict):
                        result_vars.update(detail_data["data"])
                    extra_vars["result"] = result_vars
                extra_vars["cache"] = self._js_runtime._cache
                toc_url = JsonPathExt.fill_template(toc_url_rule, detail_data, extra_vars=extra_vars)
            else:
                result = self._runtime_facade.extract(
                    detail_data,
                    toc_url_rule,
                    operation="extract_string",
                    stage="toc_rule_js",
                    base_url=detail_base_url,
                    context=self._selector_context(source=source, stage="toc_rule_js"),
                )
                if result.success and result.value:
                    val = result.value
                    if isinstance(val, list):
                        val = next((v for v in val if v), "") if val else ""
                    if val and not isinstance(val, str):
                        val = str(val)
                    toc_url = val if isinstance(val, str) else ""

            if toc_url and not toc_url.startswith("http"):
                toc_url = UrlUtils.resolve_relative(toc_url, detail_base_url)

        final_url = toc_url if toc_url else book_url
        if not final_url:
            return []

        try:
            resp, final_base_url = await self._request_configured_url(
                final_url,
                headers=headers,
                base_url=detail_base_url,
            )
        except Exception as e:
            logger.debug(f"toc request failed {source.get('bookSourceName', '')}: {e}")
            return []

        if not resp.success:
            return []

        resp_data = self._extract_response_data(resp)
        chapter_list_rule = rule_toc.get("chapterList", "")
        if not chapter_list_rule:
            return []

        chapter_list = self._extract_list(
            resp_data,
            chapter_list_rule,
            resp.is_html,
            final_base_url,
            stage="toc",
        )
        if not chapter_list:
            return []

        name_rule = rule_toc.get("chapterName", "") or rule_toc.get("name", "")
        url_rule = rule_toc.get("chapterUrl", "") or rule_toc.get("url", "")

        chapters: list[dict[str, Any]] = []
        for idx, item in enumerate(chapter_list):
            title = self._extract_field(item, name_rule, final_base_url, resp.is_html, "name", stage="toc")
            url = self._extract_field(item, url_rule, final_base_url, resp.is_html, "url", stage="toc")
            if url and not url.startswith("http"):
                url = UrlUtils.resolve_relative(url, final_base_url)
            if title and url:
                chapters.append(
                    {
                        "title": title,
                        "url": url,
                        "index": idx,
                        "_raw": item,
                    }
                )

        return chapters

    async def get_content(
        self,
        source: Dict[str, Any],
        chapter_url: str,
    ) -> Dict[str, Any]:
        rule_content = self._parse_rule(source.get("ruleContent", {}))
        if not rule_content:
            return {"content": "", "title": "", "nextUrl": ""}

        base_url = UrlUtils.get_base_url(source.get("bookSourceUrl", ""))
        headers = UrlUtils.parse_headers(source.get("header", ""))
        try:
            resp, response_base_url = await self._request_configured_url(
                chapter_url,
                headers=headers,
                base_url=base_url,
            )
        except Exception as e:
            logger.debug(f"content request failed {source.get('bookSourceName', '')}: {e}")
            return {"content": "", "title": "", "nextUrl": ""}

        if not resp.success:
            return {"content": "", "title": "", "nextUrl": ""}

        resp_data = self._extract_response_data(resp)
        content_rule = rule_content.get("content", "")
        title_rule = rule_content.get("title", "")
        next_url_rule = rule_content.get("nextContentUrl", "") or rule_content.get("nextUrl", "")

        content = self._extract_field(resp_data, content_rule, response_base_url, resp.is_html, "content", stage="content")
        title = self._extract_field(resp_data, title_rule, response_base_url, resp.is_html, "name", stage="content")
        next_url = self._extract_field(resp_data, next_url_rule, response_base_url, resp.is_html, "url", stage="content")

        if next_url and not next_url.startswith("http"):
            next_url = UrlUtils.resolve_relative(next_url, response_base_url)

        if content:
            replace_rule = (
                source.get("replaceRule", "")
                or rule_content.get("replaceRule", "")
                or rule_content.get("replaceRegex", "")
            )
            content = TextPipeline.clean_content(content, replace_rule)

        return {
            "content": content or "",
            "title": title or "",
            "nextUrl": next_url or "",
        }

    async def get_book_info(
        self,
        source: Dict[str, Any],
        book_url: str,
    ) -> Dict[str, Any]:
        rule_book_info = self._parse_rule(source.get("ruleBookInfo", {}))
        if not rule_book_info:
            return {}

        headers = UrlUtils.parse_headers(source.get("header", ""))
        try:
            resp, response_base_url = await self._request_configured_url(
                book_url,
                headers=headers,
                base_url=UrlUtils.get_base_url(source.get("bookSourceUrl", "")),
            )
        except Exception:
            return {}

        if not resp.success:
            return {}

        resp_data = self._extract_response_data(resp)
        info: dict[str, Any] = {}
        for field in ["name", "author", "intro", "coverUrl", "kind", "lastChapter", "wordCount", "lastUpdate"]:
            rule = rule_book_info.get(field, "")
            if rule:
                info[field] = self._extract_field(
                    resp_data,
                    rule,
                    response_base_url,
                    resp.is_html,
                    field,
                    stage="book_info",
                )
        return info

    async def _request_configured_url(
        self,
        raw_url: str,
        headers: dict[str, str],
        base_url: str,
    ) -> tuple[HttpResponse, str]:
        request_url, method, body = UrlUtils.parse_search_url(raw_url)
        if not request_url.startswith("http"):
            request_url = UrlUtils.resolve_relative(request_url, base_url)
        if method == "POST":
            if isinstance(body, str) and body.lstrip().startswith(("{", "[")):
                try:
                    response = await self._http.post(
                        request_url,
                        json_data=json.loads(body),
                        headers=headers,
                    )
                except json.JSONDecodeError:
                    response = await self._http.post(request_url, data=body, headers=headers)
            else:
                response = await self._http.post(request_url, data=body, headers=headers)
        else:
            response = await self._http.get(request_url, headers=headers)
        return response, response.url or request_url

    @staticmethod
    def _parse_rule(rule: Any) -> Dict[str, Any]:
        if not rule:
            return {}
        if isinstance(rule, dict):
            return rule
        if isinstance(rule, str):
            try:
                return json.loads(rule)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    @staticmethod
    def _extract_response_data(resp: HttpResponse) -> Any:
        if resp.is_json and resp.json_data is not None:
            return resp.json_data
        return resp.text

    def _extract_list(
        self,
        data: Any,
        rule: str,
        is_html: bool,
        base_url: str,
        stage: str = "unknown",
    ) -> List[Any]:
        if not rule:
            return []
        result = self._runtime_facade.extract(
            data,
            rule,
            operation="extract_list",
            stage=stage,
            base_url=base_url,
            context=self._selector_context(stage=stage),
        )
        if not result.success or result.value is None:
            return []
        return result.value if isinstance(result.value, list) else [result.value]

    def _extract_field(
        self,
        data: Any,
        rule: str,
        base_url: str,
        is_html: bool,
        field_type: str = "",
        stage: str = "unknown",
    ) -> str:
        if not rule:
            return ""

        has_inline_js = any(marker in rule for marker in ("\n@js:", "@js:", "\n<js>", "<js>"))
        if isinstance(data, dict) and "{{" in rule and "}}" in rule and not has_inline_js:
            value = JsonPathExt.fill_template(
                rule,
                data,
                extra_vars={
                    "baseUrl": base_url,
                    "cache": self._js_runtime._cache,
                },
            )
        else:
            result = self._runtime_facade.extract(
                data,
                rule,
                operation="extract_string",
                stage=stage,
                base_url=base_url,
                context=self._selector_context(),
            )
            if not result.success or result.value is None:
                return ""
            value = result.value

        if isinstance(value, list):
            if not value:
                return ""
            if field_type in ("content", "intro"):
                parts = [str(v) for v in value if v]
                value = "\n".join(parts)
            else:
                value = value[0]

        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        else:
            value = str(value)

        url_fields = {"url", "bookUrl", "coverUrl", "nextUrl", "tocUrl", "chapterUrl"}
        if field_type in url_fields and value and not value.startswith("http"):
            value = UrlUtils.resolve_relative(value, base_url)

        return value

    def runtime_diagnostics(self) -> dict[str, Any]:
        facade = self._runtime_facade
        client = getattr(facade, "native_client", None)
        return {
            "mode": getattr(facade, "mode", ""),
            "diffs": list(getattr(facade, "diffs", [])),
            "restart_count": int(getattr(client, "restart_count", 0)),
        }

    async def close(self):
        try:
            http_close = self._http.close()
            if inspect.isawaitable(http_close):
                await http_close
        finally:
            runtime_close = getattr(self._js_runtime, 'close', None)
            if callable(runtime_close):
                result = runtime_close()
                if inspect.isawaitable(result):
                    await result
            facade_close = getattr(self._runtime_facade, "close", None)
            if callable(facade_close):
                result = facade_close()
                if inspect.isawaitable(result):
                    await result

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
