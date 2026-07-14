from __future__ import annotations

import json
import select
import subprocess
import time
from pathlib import Path

from app.infrastructure.legado.engine.js_session_models import (
    JsExecutionContext,
    JsExecutionTrace,
)


class JsWorkerOutput:
    def __init__(
        self,
        success: bool,
        value=None,
        cache_updates=None,
        error_code: str | None = None,
        error: str | None = None,
        trace: JsExecutionTrace | None = None,
    ):
        self.success = success
        self.value = value
        self.cache_updates = cache_updates or {}
        self.error_code = error_code
        self.error = error
        self.trace = trace or JsExecutionTrace(
            stage="unknown",
            success=success,
            rule_preview="",
        )


class JsWorkerClient:
    def __init__(
        self,
        node_binary: str = "node",
        worker_path: Path | None = None,
        bridge_http_handler=None,
        response_timeout_seconds: float = 8.0,
    ):
        if response_timeout_seconds <= 0:
            raise ValueError('response_timeout_seconds must be positive')
        self._node_binary = node_binary
        self._worker_path = worker_path or Path(__file__).resolve().parents[4] / "nodejs" / "legado_js_worker.js"
        self._bridge_http_handler = bridge_http_handler
        self._response_timeout_seconds = response_timeout_seconds
        self._process: subprocess.Popen[str] | None = None

    def _ensure_started(self) -> None:
        if self._process and self._process.poll() is None:
            return

        self._process = subprocess.Popen(
            [self._node_binary, str(self._worker_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

    def execute(self, code: str, context: JsExecutionContext) -> JsWorkerOutput:
        self._ensure_started()
        started_at = time.time()
        payload = {
            "type": "execute",
            "code": code,
            "context": {
                "stage": context.stage,
                "source": context.source,
                "book": context.book,
                "result": context.result,
                "baseUrl": context.base_url,
                "cache": context.cache,
                "variables": context.variables,
                "headers": context.headers,
            },
        }

        assert self._process is not None
        assert self._process.stdin is not None
        assert self._process.stdout is not None

        try:
            self._process.stdin.write(
                json.dumps(payload, ensure_ascii=False, default=self._json_default) + "\n"
            )
            self._process.stdin.flush()
        except (BrokenPipeError, OSError):
            return self._failed_output(context, code, started_at, 'WORKER_IO_ERROR')

        deadline = time.monotonic() + self._response_timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self._timeout_output(context, code, started_at)
            try:
                ready, _, _ = select.select([self._process.stdout], [], [], remaining)
            except (OSError, ValueError):
                return self._failed_output(context, code, started_at, 'WORKER_IO_ERROR')
            if not ready:
                return self._timeout_output(context, code, started_at)
            raw = self._process.stdout.readline()
            if not raw:
                return self._failed_output(context, code, started_at, 'WORKER_EOF')
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                return self._failed_output(context, code, started_at, 'MALFORMED_RESPONSE')
            if not isinstance(message, dict):
                return self._failed_output(context, code, started_at, 'MALFORMED_RESPONSE')
            if message.get("type") == "bridge_http":
                if not isinstance(message.get('request'), dict) or not message.get('id'):
                    return self._failed_output(context, code, started_at, 'MALFORMED_RESPONSE')
                response = (
                    self._bridge_http_handler(message["request"])
                    if self._bridge_http_handler
                    else {"status": 500, "text": "bridge handler missing", "headers": {}}
                )
                try:
                    self._process.stdin.write(
                        json.dumps(
                            {
                                "type": "bridge_http_result",
                                "id": message["id"],
                                "response": response,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    self._process.stdin.flush()
                except (BrokenPipeError, OSError, KeyError):
                    return self._failed_output(context, code, started_at, 'WORKER_IO_ERROR')
                continue
            break

        elapsed_ms = int((time.time() - started_at) * 1000)
        trace = JsExecutionTrace(
            stage=context.stage,
            success=bool(message.get("success")),
            rule_preview=code[:120],
            worker_elapsed_ms=elapsed_ms,
            bridge_http_count=int(message.get("bridge_http_count", 0)),
            cache_keys_written=sorted((message.get("cache") or {}).keys()),
            error_code=message.get("error_code"),
        )
        return JsWorkerOutput(
            success=bool(message.get("success")),
            value=message.get("value"),
            cache_updates=message.get("cache") or {},
            error_code=message.get("error_code"),
            error=message.get("error"),
            trace=trace,
        )

    def close(self) -> None:
        self._terminate_process()

    def _timeout_output(self, context: JsExecutionContext, code: str, started_at: float) -> JsWorkerOutput:
        self._terminate_process()
        return self._failed_output(context, code, started_at, 'EXECUTION_TIMEOUT')

    def _failed_output(
        self,
        context: JsExecutionContext,
        code: str,
        started_at: float,
        error_code: str,
    ) -> JsWorkerOutput:
        trace = JsExecutionTrace(
            stage=context.stage,
            success=False,
            rule_preview=code[:120],
            worker_elapsed_ms=int((time.time() - started_at) * 1000),
            error_code=error_code,
        )
        return JsWorkerOutput(
            success=False,
            error_code=error_code,
            error=None,
            trace=trace,
        )

    def _terminate_process(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)

    @staticmethod
    def _json_default(value):
        return str(value)
