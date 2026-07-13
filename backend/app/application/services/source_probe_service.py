from __future__ import annotations

import time
import re
from urllib.parse import quote

from app.application.services.source_health_models import SourceProbeEvidence, StageProbeResult
from app.infrastructure.legado.engine.url_utils import UrlUtils


class SourceProbeService:
    def __init__(self, fetcher):
        self._fetcher = fetcher

    async def aclose(self):
        close = getattr(self._fetcher, "close", None)
        if close is not None:
            await close()

    async def probe_source(
        self,
        source: dict,
        keyword_samples: list[str],
        probe_mode: str = "full_chain",
    ) -> SourceProbeEvidence:
        keyword = keyword_samples[0]
        preflight = self._build_search_preflight(source, keyword)

        search_started = time.perf_counter()
        try:
            found = await self._fetcher.search(source, keyword, page=1)
            detail = dict(preflight.get("detail") or {})
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
                    detail={"first_chapter": chapters[0] if chapters else {}},
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
