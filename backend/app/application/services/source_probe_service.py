from __future__ import annotations

import time
import re
from copy import deepcopy
from urllib.parse import quote, urlencode, urljoin

from bs4 import BeautifulSoup, Tag

from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult
from app.infrastructure.legado.engine.url_utils import UrlUtils


class SourceProbeService:
    def __init__(self, fetcher):
        self._fetcher = fetcher

    def set_execution_deadline(self, deadline: float | None) -> None:
        setter = getattr(self._fetcher, 'set_execution_deadline', None)
        if callable(setter):
            setter(deadline)

    async def aclose(self):
        close = getattr(self._fetcher, "close", None)
        if close is not None:
            await close()

    async def synthesize_source_rule(
        self,
        *,
        source: dict,
        entry_url: str,
        keyword: str,
    ) -> dict:
        """Infer a portable Legado rule from a public HTML search flow."""
        http = getattr(self._fetcher, "_http", None)
        get = getattr(http, "get", None)
        post = getattr(http, "post", None)
        if not callable(get) or not callable(post):
            return source

        result = deepcopy(source)
        headers = UrlUtils.parse_headers(result.get("header", ""))
        try:
            entry_response = await get(entry_url, headers=headers)
            if not _is_html_success(entry_response):
                return source
            entry_base_url = getattr(entry_response, "url", "") or entry_url
            form = _find_search_form(entry_response.text)
            if form is None:
                return source

            field_name, action_url, method = _search_form_request(form, entry_base_url)
            if not field_name or not action_url:
                return source
            encoded_body = urlencode({field_name: keyword})
            if method == "POST":
                headers = {
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                search_response = await post(action_url, data=encoded_body, headers=headers)
                search_url = f"{action_url}::POST\n{field_name}={{{{key}}}}"
            else:
                separator = "&" if "?" in action_url else "?"
                search_url = f"{action_url}{separator}{field_name}={{{{key}}}}"
                search_response = await get(f"{action_url}{separator}{encoded_body}", headers=headers)
            if not _is_html_success(search_response):
                return source

            search_rules, selected_book_url = _discover_search_rules(
                BeautifulSoup(search_response.text, "lxml"),
                keyword=keyword,
                base_url=getattr(search_response, "url", "") or action_url,
            )
            if not search_rules or not selected_book_url:
                return source

            book_response = await get(selected_book_url, headers=headers)
            if not _is_html_success(book_response):
                return source
            toc_rules, selected_chapter_url = _discover_toc_rules(
                BeautifulSoup(book_response.text, "lxml"),
                base_url=getattr(book_response, "url", "") or selected_book_url,
            )
            if not toc_rules or not selected_chapter_url:
                return source

            chapter_response = await get(selected_chapter_url, headers=headers)
            if not _is_html_success(chapter_response):
                return source
            content_rule = _discover_content_rule(BeautifulSoup(chapter_response.text, "lxml"))
            if not content_rule:
                return source

            result.update(
                {
                    "searchUrl": search_url,
                    "ruleSearch": search_rules,
                    "ruleToc": toc_rules,
                    "ruleContent": {"content": content_rule},
                    "header": _format_headers(headers),
                    "bookSourceComment": "[source-build] public HTML form and DOM synthesis",
                }
            )
            return result
        except Exception:
            return source

    async def probe_source(
        self,
        source: dict,
        keyword_samples: list[str],
        probe_mode: str = "full_chain",
    ) -> SourceProbeEvidence:
        keywords = self._normalize_keywords(keyword_samples)
        attempts: list[dict] = []
        selected: SourceProbeEvidence | None = None

        for keyword in keywords:
            candidate = await self._probe_single_keyword(
                source=source,
                keyword=keyword,
                probe_mode=probe_mode,
            )
            attempts.append(
                {
                    "keyword": keyword,
                    "search_status": candidate.search.status,
                    "search_hits": candidate.search.hit_count,
                    "toc_status": candidate.toc.status,
                    "content_status": candidate.content.status,
                    "error_message": candidate.search.error_message,
                }
            )
            if selected is None or self._probe_quality(candidate) > self._probe_quality(selected):
                selected = candidate
            chain_succeeded = (
                candidate.search.status == "ok"
                and (
                    probe_mode != "full_chain"
                    or (candidate.toc.status == "ok" and candidate.content.status == "ok")
                )
            )
            if chain_succeeded:
                selected = candidate
                break

        if selected is None:
            selected = await self._probe_single_keyword(
                source=source,
                keyword="捞尸人",
                probe_mode=probe_mode,
            )
            attempts.append(
                {
                    "keyword": "捞尸人",
                    "search_status": selected.search.status,
                    "search_hits": selected.search.hit_count,
                    "toc_status": selected.toc.status,
                    "content_status": selected.content.status,
                    "error_message": selected.search.error_message,
                }
            )

        selected.attempted_keywords = [item["keyword"] for item in attempts]
        selected.attempts = attempts
        return selected

    @staticmethod
    def _normalize_keywords(keyword_samples: list[str] | None) -> list[str]:
        normalized: list[str] = []
        for value in keyword_samples or []:
            keyword = str(value or "").strip()
            if keyword and keyword not in normalized:
                normalized.append(keyword)
        return normalized or ["捞尸人", "斗罗大陆", "剑来"]

    @staticmethod
    def _probe_quality(evidence: SourceProbeEvidence) -> tuple[int, int, int, int]:
        return (
            int(evidence.search.status == "ok"),
            int(evidence.toc.status == "ok"),
            int(evidence.content.status == "ok"),
            evidence.search.hit_count,
        )

    async def _probe_single_keyword(
        self,
        *,
        source: dict,
        keyword: str,
        probe_mode: str,
    ) -> SourceProbeEvidence:
        preflight = self._build_search_preflight(source, keyword)

        search_started = time.perf_counter()
        try:
            found = await self._fetcher.search(source, keyword, page=1)
            detail = dict(preflight.get("detail") or {})
            runtime_detail = self._runtime_diagnostics()
            if runtime_detail:
                detail["runtime"] = runtime_detail
            if not found:
                detail.update(await self._collect_transport_evidence(source, preflight))
            if found:
                detail["top_hit"] = found[0]
            search = StageProbeResult(
                stage="search",
                status="ok" if found else "failed",
                elapsed_ms=int((time.perf_counter() - search_started) * 1000),
                request_preview=preflight.get("request_preview", ""),
                hit_count=len(found),
                sample_title=found[0].get("name", "") if found else "",
                error_message=preflight.get("error_message", ""),
                detail=detail,
            )
        except Exception as exc:
            found = []
            search = StageProbeResult(
                stage="search",
                status="failed",
                elapsed_ms=int((time.perf_counter() - search_started) * 1000),
                request_preview=preflight.get("request_preview", ""),
                error_message=" | ".join(
                    part for part in [preflight.get("error_message", ""), str(exc)] if part
                ),
                detail=dict(preflight.get("detail") or {}),
            )

        toc = StageProbeResult(stage="toc", status="skipped")
        content = StageProbeResult(stage="content", status="skipped")

        if probe_mode == "full_chain" and found:
            book_url = found[0].get("bookUrl", "")
            toc_started = time.perf_counter()
            try:
                chapters = await self._fetcher.get_toc(source, book_url)
                toc = StageProbeResult(
                    stage="toc",
                    status="ok" if chapters else "failed",
                    elapsed_ms=int((time.perf_counter() - toc_started) * 1000),
                    hit_count=len(chapters),
                    sample_title=chapters[0].get("title", "") if chapters else "",
                    detail={"first_chapter": _chapter_evidence(chapters[0]) if chapters else {}},
                )
                if not chapters:
                    toc.detail.update(
                        await self._collect_stage_transport_evidence(
                            source,
                            book_url,
                            parse_status="empty",
                        )
                    )
            except Exception as exc:
                chapters = []
                toc = StageProbeResult(
                    stage="toc",
                    status="failed",
                    elapsed_ms=int((time.perf_counter() - toc_started) * 1000),
                    error_message=str(exc),
                )

            if chapters:
                content_started = time.perf_counter()
                try:
                    payload = await self._fetcher.get_content(source, chapters[0]["url"])
                    body = payload.get("content", "")
                    content = StageProbeResult(
                        stage="content",
                        status="ok" if body else "failed",
                        elapsed_ms=int((time.perf_counter() - content_started) * 1000),
                        sample_title=payload.get("title", ""),
                        detail={"content_length": len(body)},
                    )
                    if not body:
                        content.detail.update(
                            await self._collect_stage_transport_evidence(
                                source,
                                chapters[0]["url"],
                                parse_status="empty",
                            )
                        )
                except Exception as exc:
                    content = StageProbeResult(
                        stage="content",
                        status="failed",
                        elapsed_ms=int((time.perf_counter() - content_started) * 1000),
                        error_message=str(exc),
                    )

        return SourceProbeEvidence(
            source_id=source["id"],
            source_name=source.get("bookSourceName", ""),
            source_url=source.get("bookSourceUrl", ""),
            probe_mode=probe_mode,
            keyword=keyword,
            search=search,
            toc=toc,
            content=content,
        )

    def _runtime_diagnostics(self) -> dict:
        getter = getattr(self._fetcher, "runtime_diagnostics", None)
        if not callable(getter):
            return {}
        try:
            value = getter()
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    def _build_search_preflight(self, source: dict, keyword: str) -> dict:
        search_url = str(source.get("searchUrl", "") or "").strip()
        if not search_url.startswith("@js:"):
            return {}

        js_runtime = getattr(self._fetcher, "_js_runtime", None)
        coerce = getattr(self._fetcher, "_coerce_js_search_output", None)
        if js_runtime is None or coerce is None:
            return {}

        base_url = UrlUtils.get_base_url(source.get("bookSourceUrl", ""))
        headers = UrlUtils.parse_headers(source.get("header", ""))
        code = search_url[4:].strip()
        raw_key = self._js_search_prefers_raw_key(code)
        encoded_keyword = keyword if raw_key else quote(keyword)
        variables = {
            "keyword": keyword,
            "key": encoded_keyword,
            "searchKey": encoded_keyword,
            "searchkey": encoded_keyword,
            "page": 1,
            "start": 0,
            "limit": 20,
            "size": 20,
            "pageSize": 20,
        }

        output = js_runtime.execute_with_metadata(
            code,
            data=None,
            stage="search_url_js",
            source=source,
            baseUrl=base_url,
            variables=variables,
            headers=headers,
        )
        detail = {
            "js_exec_status": "ok" if output.success else "fail",
        }
        if output.success:
            detail["js_result_preview"] = str(output.value)[:200]
            request_spec, _ = coerce(output.value, base_url=base_url)
            preview = str(output.value)[:200]
            if request_spec:
                request_url = str(request_spec.get("url", "") or "")
                if request_url and not request_url.startswith("http"):
                    request_url = UrlUtils.resolve_relative(request_url, base_url)
                request_spec = {**request_spec, "url": request_url}
                preview = request_url
                request_body = request_spec.get("body")
                if request_body not in {None, ""}:
                    preview = f"{preview} BODY={request_body}"
            return {
                "request_preview": preview,
                "error_message": "",
                "detail": detail,
                "request_spec": request_spec,
            }

        detail["js_error"] = output.error or output.error_code or "js execution failed"
        return {
            "request_preview": "",
            "error_message": detail["js_error"],
            "detail": detail,
        }

    def _js_search_prefers_raw_key(self, code: str) -> bool:
        matcher = getattr(self._fetcher, "js_search_prefers_raw_key", None)
        if matcher is not None:
            return bool(matcher(code))
        return bool(re.search(r"\bkey\.(?:charAt|slice|startsWith|substring)\s*\(", code or ""))

    async def _collect_transport_evidence(self, source: dict, preflight: dict) -> dict:
        request_spec = preflight.get("request_spec")
        http_client = getattr(self._fetcher, "_http", None)
        if not request_spec or http_client is None:
            return {}

        request_url = request_spec.get("url", "")
        if not request_url:
            return {}
        headers = {
            **UrlUtils.parse_headers(source.get("header", "")),
            **(request_spec.get("headers") or {}),
        }
        method = str(request_spec.get("method", "GET") or "GET").upper()
        try:
            if method == "POST":
                body = request_spec.get("body")
                if isinstance(body, dict):
                    response = await http_client.post(request_url, json_data=body, headers=headers)
                else:
                    response = await http_client.post(request_url, data=body, headers=headers)
            else:
                response = await http_client.get(request_url, headers=headers)
        except Exception as exc:
            return {
                "http_status": 0,
                "http_error": str(exc),
                "response_kind": "network_error",
            }

        return self._response_diagnostics(response)

    async def _collect_stage_transport_evidence(
        self,
        source: dict,
        raw_url: str,
        *,
        parse_status: str,
    ) -> dict:
        request = getattr(self._fetcher, "_request_configured_url", None)
        if request is None or not raw_url:
            return {"parse_status": parse_status}

        try:
            response, _ = await request(
                raw_url,
                headers=UrlUtils.parse_headers(source.get("header", "")),
                base_url=UrlUtils.get_base_url(source.get("bookSourceUrl", "")),
            )
        except Exception as exc:
            return {
                "http_status": 0,
                "http_error": str(exc),
                "response_kind": "network_error",
                "expected_response_kind": "json",
                "parse_status": parse_status,
            }
        return self._response_diagnostics(response, parse_status=parse_status)

    @staticmethod
    def _response_diagnostics(response, *, parse_status: str = "unknown") -> dict:
        response_kind = "json" if response.is_json else ("html" if response.is_html else "text")
        response_preview = re.sub(
            r"(?i)(cookie|authorization)\s*[:=]\s*[^;\s]+",
            r"\1=[redacted]",
            response.text or "",
        )[:300]
        is_verification_wall = (
            response_kind == "html"
            and (
                "/user/verify" in str(getattr(response, "url", "")).lower()
                or 'getcookie("getsite")' in (response.text or "").lower()
            )
        )
        return {
            "http_status": response.status,
            "http_error": response.error or "",
            "response_kind": response_kind,
            "response_preview": response_preview,
            "expected_response_kind": "json",
            "parse_status": "content_access_blocked" if is_verification_wall else parse_status,
            **({"block_reason": "verification_wall"} if is_verification_wall else {}),
            "http_elapsed_ms": response.elapsed_ms,
        }


def _is_html_success(response) -> bool:
    return bool(getattr(response, "success", False) and getattr(response, "is_html", False))


def _chapter_evidence(chapter: dict) -> dict:
    return {
        key: chapter[key]
        for key in ("title", "url", "index")
        if key in chapter
    }


def _find_search_form(document: str) -> Tag | None:
    soup = BeautifulSoup(document, "lxml")
    for form in soup.find_all("form"):
        for field in form.find_all("input"):
            name = str(field.get("name") or "").strip()
            field_type = str(field.get("type") or "text").lower()
            if name and field_type in {"text", "search"}:
                return form
    return None


def _search_form_request(form: Tag, base_url: str) -> tuple[str, str, str]:
    field = next(
        (
            item
            for item in form.find_all("input")
            if str(item.get("name") or "").strip()
            and str(item.get("type") or "text").lower() in {"text", "search"}
        ),
        None,
    )
    if field is None:
        return "", "", "GET"
    return (
        str(field.get("name")).strip(),
        urljoin(base_url, str(form.get("action") or base_url)),
        str(form.get("method") or "GET").upper(),
    )


def _discover_search_rules(document: BeautifulSoup, *, keyword: str, base_url: str) -> tuple[dict, str]:
    anchor = next(
        (
            item
            for item in document.find_all("a", href=True)
            if keyword in item.get_text(" ", strip=True)
        ),
        None,
    )
    if anchor is None:
        return {}, ""
    item = _repeated_result_card(anchor)
    if item is None:
        return {}, ""
    container = item.parent
    if not isinstance(container, Tag):
        return {}, ""
    title_rule = _relative_css(anchor, item)
    if not title_rule:
        return {}, ""
    author = _author_node(item, anchor)
    rules = {
        "bookList": f"@css:{_css_selector(container)} > {_css_selector(item)}",
        "name": f"@css:{title_rule}@text",
        "bookUrl": f"@css:{title_rule}@href",
    }
    if author is not None:
        author_rule = _relative_css(author, item)
        if author_rule:
            rules["author"] = f"@css:{author_rule}@text"
    return rules, urljoin(base_url, str(anchor.get("href") or ""))


def _repeated_result_card(anchor: Tag) -> Tag | None:
    """Return the nearest result card repeated among its parent's children."""
    for item in [anchor, *anchor.parents]:
        if not isinstance(item, Tag) or item.name not in {"li", "article", "tr", "dl", "div"}:
            continue
        container = item.parent
        if not isinstance(container, Tag):
            continue
        selector = _css_selector(item)
        cards = [
            child
            for child in container.find_all(item.name, recursive=False)
            if _css_selector(child) == selector
        ]
        if len(cards) >= 2:
            return item
    return None


def _author_node(item: Tag, anchor: Tag) -> Tag | None:
    class_author = item.select_one(".author")
    if class_author is not None:
        return class_author
    title_parent = anchor.parent
    if not isinstance(title_parent, Tag):
        return None
    seen_title = False
    for sibling in item.find_all(["span", "p", "dd"], recursive=False):
        if sibling is title_parent:
            seen_title = True
            continue
        if seen_title and sibling.get_text(" ", strip=True):
            return sibling
    return None


def _discover_toc_rules(document: BeautifulSoup, *, base_url: str) -> tuple[dict, str]:
    container, chapters = _best_chapter_container(document)
    if container is None or not chapters:
        return {}, ""
    chapter = chapters[0]
    if chapter.parent is not None and chapter.parent.name == "li" and chapter.parent.parent is container:
        chapter_selector = f"{_css_selector(container)} > li > a"
    else:
        chapter_selector = f"{_css_selector(container)} a"
    return {
        "chapterList": f"@css:{chapter_selector}",
        "chapterName": "@css:text",
        "chapterUrl": "@css:href",
    }, urljoin(base_url, str(chapter.get("href") or ""))


def _best_chapter_container(document: BeautifulSoup) -> tuple[Tag | None, list[Tag]]:
    candidates: list[tuple[tuple[int, int, int], Tag, list[Tag]]] = []
    for container in document.find_all(["ul", "ol", "dl", "div"]):
        chapters = [
            item for item in container.find_all("a", href=True)
            if re.match(
                r"^(?:第|序章|引子|楔子|chapter(?:\s|:|-))",
                item.get_text(" ", strip=True),
                flags=re.IGNORECASE,
            )
        ]
        if len(chapters) < 2:
            continue
        marker = " ".join([str(container.get("id") or ""), *container.get("class", [])]).lower()
        marker_score = sum(token in marker for token in ("chapter", "catalog", "directory", "dir", "list"))
        tag_score = 2 if container.name in {"ul", "ol", "dl"} else 1
        candidates.append(((tag_score, marker_score, len(chapters)), container, chapters))
    if not candidates:
        return None, []
    _, container, chapters = max(candidates, key=lambda item: item[0])
    return container, chapters


def _discover_content_rule(document: BeautifulSoup) -> str:
    candidates = []
    for item in document.find_all(["article", "div", "section"]):
        marker = " ".join([str(item.get("id") or ""), *item.get("class", [])]).lower()
        text = item.get_text(" ", strip=True)
        if marker and any(token in marker for token in ("content", "chapter", "read", "text")) and text:
            candidates.append((len(text), item))
    if not candidates:
        return ""
    return f"@css:{_css_selector(max(candidates, key=lambda item: item[0])[1])}@html"


def _relative_css(node: Tag, ancestor: Tag) -> str:
    parts = []
    current: Tag | None = node
    while current is not None and current is not ancestor:
        parts.append(_css_selector(current))
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return " > ".join(reversed(parts)) if current is ancestor else ""


def _css_selector(node: Tag) -> str:
    node_id = str(node.get("id") or "").strip()
    if node_id:
        return f"#{node_id}"
    classes = [
        str(name).strip()
        for name in node.get("class", [])
        if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", str(name))
    ]
    return f"{node.name}{''.join(f'.{name}' for name in classes)}"


def _format_headers(headers: dict[str, str]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in headers.items())
