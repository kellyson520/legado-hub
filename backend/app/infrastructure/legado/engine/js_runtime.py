"""
Legado JS runtime facade.

保留旧的 `execute()` 值返回接口，同时新增 `execute_with_metadata()`
供服务端原生语义兼容层、trace、compat diff 和 worker bridge 使用。
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx  # compatibility surface for integrations that patch the legacy client

from app.core.url_safety import public_http_url_error
from app.infrastructure.http.outbound import SafeSyncHttpClient
from app.infrastructure.legado.engine.jsonpath_ext import JsonPathExt
from app.infrastructure.legado.engine.js_session_models import (
    JsCompatDiff,
    JsExecutionTrace,
)
from app.infrastructure.legado.engine.js_worker_bridge import JsWorkerClient
from app.infrastructure.legado.engine.runtime_bridge import RuntimeBridge
from app.infrastructure.legado.engine.legado_native_semantics import (
    LegadoJsCompatProfile,
)
from app.core.logging import get_logger

logger = get_logger("legado_js")


@dataclass
class JsResult:
    success: bool
    value: Any = None
    error: Optional[str] = None


@dataclass
class JsInvocationResult:
    success: bool
    value: Any = None
    error_code: str | None = None
    error: str | None = None
    trace: JsExecutionTrace | None = None
    cache_updates: dict[str, Any] | None = None
    compat_diff: JsCompatDiff | None = None


class JsRuntime:
    def __init__(
        self,
        worker_client: JsWorkerClient | None = None,
        compat_profile: LegadoJsCompatProfile | None = None,
        runtime_bridge: RuntimeBridge | None = None,
    ):
        self._context: Dict[str, Any] = {}
        self._cache: Dict[str, Any] = {}
        self._worker = worker_client or JsWorkerClient(
            bridge_http_handler=self._handle_bridge_http,
        )
        self._runtime_bridge = runtime_bridge
        self._compat_profile = compat_profile or LegadoJsCompatProfile.native_defaults()
        if hasattr(self._worker, "_bridge_http_handler"):
            self._worker._bridge_http_handler = self._handle_bridge_http

    def close(self):
        close = getattr(self._worker, 'close', None)
        return close() if callable(close) else None

    def set_execution_deadline(self, deadline: float | None) -> None:
        setter = getattr(self._worker, 'set_execution_deadline', None)
        if callable(setter):
            setter(deadline)

    def _handle_bridge_http(self, request_spec: dict[str, Any]) -> dict[str, Any]:
        if self._runtime_bridge is not None:
            return self._runtime_bridge.handle(request_spec)
        url = str(request_spec.get("url", "") or "")
        if not url:
            return {
                "status": 400,
                "text": "empty url for js bridge request",
                "headers": {},
            }

        method = str(request_spec.get("method", "GET") or "GET").upper()
        headers = {
            str(key): str(value)
            for key, value in (request_spec.get("headers") or {}).items()
        }
        headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
        )
        body = request_spec.get("body")
        follow_redirects = bool(request_spec.get("follow_redirects", False))
        url_error = public_http_url_error(url)
        if url_error is not None:
            return {
                "status": 400,
                "text": f"unsafe url for js bridge request: {url_error}",
                "headers": {},
            }
        try:
            with SafeSyncHttpClient(
                follow_redirects=follow_redirects,
                timeout=15.0,
            ) as client:
                if method == "POST":
                    if isinstance(body, (dict, list)):
                        response = client.post(url, json=body, headers=headers)
                    elif body is None:
                        response = client.post(url, headers=headers)
                    else:
                        response = client.post(url, content=body if isinstance(body, bytes) else str(body), headers=headers)
                else:
                    response = client.request(method, url, headers=headers)
                text = response.text
                return {
                    "status": response.status_code,
                    "text": text,
                    "headers": dict(response.headers.items()),
                }
        except Exception as exc:
            return {
                "status": 599,
                "text": str(exc),
                "headers": {},
            }

    def execute_with_metadata(
        self,
        code: str,
        data: Any = None,
        expected_value: Any = None,
        expected_cache: dict[str, Any] | None = None,
        **kwargs,
    ) -> JsInvocationResult:
        if not code:
            return JsInvocationResult(
                success=False,
                error_code="EMPTY_CODE",
                error="empty js code",
            )

        raw_code = code.strip()
        context = self._compat_profile.build_context(
            stage=kwargs.get("stage", "search_rule_js"),
            source=kwargs.get("source"),
            book=kwargs.get("book"),
            result=data,
            base_url=kwargs.get("baseUrl", ""),
            cache=self._cache,
            variables=kwargs.get("variables"),
            headers=kwargs.get("headers"),
        )
        raw_code = self._render_code_templates(raw_code, context.variables, kwargs)
        raw_code = self._render_jsonpath_templates(raw_code, data)

        builtin_context = {
            **kwargs,
            "result": data,
            "java": JsJavaBridge(),
            "source": kwargs.get("source", {}),
            "book": kwargs.get("book", {}),
            "cache": JsCacheBridge(self._cache),
        }
        if "JSON.parse(result)" in raw_code and isinstance(builtin_context.get("result"), (dict, list)):
            builtin_context["result"] = json.dumps(builtin_context["result"], ensure_ascii=False)

        builtin_result = self._try_builtin_patterns(raw_code, builtin_context)
        if builtin_result is not None:
            trace = JsExecutionTrace(
                stage=context.stage,
                success=True,
                rule_preview=raw_code[:120],
                builtin_hit=True,
            )
            return JsInvocationResult(
                success=True,
                value=builtin_result,
                trace=trace,
                cache_updates={},
                compat_diff=self._build_compat_diff(
                    expected_value=expected_value,
                    actual_value=builtin_result,
                    expected_cache=expected_cache,
                    trace=trace,
                ),
            )

        prepared_code = self._prepare_node_code(raw_code)
        worker_output = self._worker.execute(prepared_code, context)
        self._cache.update(worker_output.cache_updates)
        return JsInvocationResult(
            success=worker_output.success,
            value=worker_output.value,
            error_code=worker_output.error_code,
            error=worker_output.error,
            trace=worker_output.trace,
            cache_updates=worker_output.cache_updates,
            compat_diff=self._build_compat_diff(
                expected_value=expected_value,
                actual_value=worker_output.value,
                expected_cache=expected_cache,
                trace=worker_output.trace,
            ),
        )

    def execute(
        self,
        code: str,
        data: Any = None,
        **kwargs,
    ) -> Any:
        output = self.execute_with_metadata(code, data=data, **kwargs)
        if output.success:
            return output.value

        logger.debug(f"JS execution failed: {output.error_code or output.error or code[:50]}")
        return None

    def _build_compat_diff(
        self,
        expected_value: Any,
        actual_value: Any,
        expected_cache: dict[str, Any] | None,
        trace: JsExecutionTrace | None,
    ) -> JsCompatDiff | None:
        if expected_value is None and expected_cache is None:
            return None
        return JsCompatDiff.compare(
            expected_value=expected_value,
            actual_value=actual_value,
            expected_cache=expected_cache or {},
            actual_cache=self._cache,
            trace=trace or JsExecutionTrace(stage="unknown", success=False, rule_preview=""),
        )

    def _try_builtin_patterns(self, code: str, context: Dict[str, Any]) -> Any:
        code = code.strip()

        while code.endswith(";"):
            code = code[:-1].strip()

        if code == "result":
            return context.get("result")

        m = re.match(r'^java\.aesBase64DecodeToString\(result,\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)"\)$', code)
        if m:
            data = context.get("result", "")
            if isinstance(data, str):
                try:
                    return base64.b64decode(data).decode("utf-8", errors="replace")
                except Exception:
                    return data
            return data

        if code == "java.base64Decode(result)":
            data = context.get("result", "")
            if isinstance(data, str):
                try:
                    return base64.b64decode(data).decode("utf-8", errors="replace")
                except Exception:
                    return data
            return data

        if code == "java.base64Encode(result)":
            data = context.get("result", "")
            if isinstance(data, str):
                return base64.b64encode(data.encode("utf-8")).decode("ascii")
            return data

        m = re.match(r'^result\.replace\(/(.+?)/g?,\s*["\'](.+?)["\']\)$', code)
        if m:
            pattern = m.group(1)
            replacement = m.group(2)
            data = str(context.get("result", ""))
            try:
                return re.sub(pattern, replacement, data)
            except re.error:
                return data

        if code == "JSON.parse(result)":
            data = context.get("result", "")
            if isinstance(data, str):
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return None
            return data

        if code == "JSON.stringify(result)":
            data = context.get("result")
            try:
                return json.dumps(data, ensure_ascii=False)
            except Exception:
                return str(data)

        m = re.match(r'^result\.split\(["\'](.+?)["\']\)$', code)
        if m:
            sep = m.group(1)
            data = str(context.get("result", ""))
            return data.split(sep)

        if code == "result.trim()":
            return str(context.get("result", "")).strip()

        m = re.match(r"^result\.substring\((\d+),\s*(\d+)\)$", code)
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            data = str(context.get("result", ""))
            return data[start:end]

        if code == "result.length":
            data = context.get("result", "")
            if isinstance(data, (str, list)):
                return len(data)
            return 0

        if code.startswith("java.md5"):
            data = str(context.get("result", ""))
            return hashlib.md5(data.encode("utf-8")).hexdigest()

        return None

    @staticmethod
    def _prepare_node_code(code: str) -> str:
        stripped = code.strip()
        if not stripped:
            return stripped

        stripped = JsRuntime._auto_await_java_calls(stripped)

        if stripped.startswith("(function") or stripped.startswith("(()") or stripped.startswith("(("):
            return f"return {stripped}"

        if re.search(r"\breturn\b", stripped):
            return stripped

        span = JsRuntime._find_last_top_level_statement_span(stripped)
        if span is None:
            return stripped

        start, end = span
        statement = stripped[start:end].strip().rstrip(";")
        if not statement:
            return stripped

        if re.match(r"^(switch|if|for|while|try)\b", statement):
            return (
                f"{stripped}\n"
                "return typeof result !== 'undefined' ? result : "
                "(typeof url !== 'undefined' ? url : undefined);"
            )

        return f"{stripped[:start]}return {statement};{stripped[end:]}"

    @staticmethod
    def _auto_await_java_calls(code: str) -> str:
        return re.sub(
            r"(?<!await )java\.(get|post|ajax)\(",
            r"await java.\1(",
            code,
        )

    @staticmethod
    def _find_last_top_level_statement_span(code: str) -> tuple[int, int] | None:
        depth_paren = 0
        depth_brace = 0
        depth_bracket = 0
        in_string: str | None = None
        escaped = False
        statement_start = 0
        spans: list[tuple[int, int]] = []

        for index, char in enumerate(code):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == in_string:
                    in_string = None
                continue

            if char in {"'", '"', "`"}:
                in_string = char
                continue

            if char == "(":
                depth_paren += 1
            elif char == ")":
                depth_paren = max(depth_paren - 1, 0)
            elif char == "{":
                depth_brace += 1
            elif char == "}":
                depth_brace = max(depth_brace - 1, 0)
            elif char == "[":
                depth_bracket += 1
            elif char == "]":
                depth_bracket = max(depth_bracket - 1, 0)

            if depth_paren == depth_brace == depth_bracket == 0 and char in {"\n", ";"}:
                segment = code[statement_start:index].strip()
                if segment and not segment.startswith("//"):
                    spans.append((statement_start, index))
                statement_start = index + 1

        tail = code[statement_start:].strip()
        if tail and not tail.startswith("//"):
            spans.append((statement_start, len(code)))

        return spans[-1] if spans else None

    @staticmethod
    def _render_code_templates(
        code: str,
        variables: dict[str, Any],
        kwargs: dict[str, Any],
    ) -> str:
        if "{{" not in code or "}}" not in code:
            return code

        replacements = {
            **{key: value for key, value in (variables or {}).items()},
            "baseUrl": kwargs.get("baseUrl", ""),
        }

        def replace(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            value = replacements.get(key)
            if value is None:
                return match.group(0)
            return str(value)

        return re.sub(r"\{\{\s*([a-zA-Z_][\w]*)\s*\}\}", replace, code)

    @staticmethod
    def _render_jsonpath_templates(code: str, data: Any) -> str:
        if "{{" not in code or "}}" not in code or not isinstance(data, (dict, list)):
            return code

        def replace(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            if not expr.startswith("$."):
                return match.group(0)
            value = JsonPathExt.query(data, expr)
            if value is None:
                return match.group(0)
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            return str(value)

        return re.sub(r"\{\{\s*(\$\.[^{}]+?)\s*\}\}", replace, code)


class JsJavaBridge:
    @staticmethod
    def base64Decode(s: str) -> str:
        try:
            return base64.b64decode(s).decode("utf-8", errors="replace")
        except Exception:
            return s

    @staticmethod
    def base64Encode(s: str) -> str:
        try:
            return base64.b64encode(s.encode("utf-8")).decode("ascii")
        except Exception:
            return s

    @staticmethod
    def md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    @staticmethod
    def sha1(s: str) -> str:
        return hashlib.sha1(s.encode("utf-8")).hexdigest()

    @staticmethod
    def aesBase64DecodeToString(data: str, key: str, mode: str, iv: str) -> str:
        try:
            return base64.b64decode(data).decode("utf-8", errors="replace")
        except Exception:
            return data


class JsCacheBridge:
    def __init__(self, store: Dict[str, Any]):
        self._store = store

    def get(self, key: str) -> Any:
        return self._store.get(key)

    def put(self, key: str, value: Any):
        self._store[key] = value

    def putMemory(self, key: str, value: Any):
        self._store[key] = value

    def getFromMemory(self, key: str) -> Any:
        return self._store.get(key)

    def dump(self) -> Dict[str, Any]:
        return dict(self._store)

    def replace_all(self, values: Dict[str, Any]):
        self._store.clear()
        self._store.update(values)
