from __future__ import annotations

import json
import os
import select
import subprocess
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

from lxml import etree

from app.infrastructure.legado.engine.js_session_models import (
    JsExecutionContext,
    JsExecutionTrace,
)


BRIDGE_CALLBACK_MAX_WORKERS = 4
_BRIDGE_CALLBACK_SLOTS = threading.BoundedSemaphore(BRIDGE_CALLBACK_MAX_WORKERS)
_BRIDGE_CALLBACK_EXECUTOR = ThreadPoolExecutor(
    max_workers=BRIDGE_CALLBACK_MAX_WORKERS,
    thread_name_prefix='legado-bridge',
)


def _bridge_callback_target(handler, request: dict):
    try:
        return handler(request)
    finally:
        _BRIDGE_CALLBACK_SLOTS.release()


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
    PROCESS_TERMINATE_WAIT_SECONDS = 0.1

    def __init__(
        self,
        node_binary: str = "node",
        worker_path: Path | None = None,
        bridge_http_handler=None,
        response_timeout_seconds: float = 8.0,
        max_response_bytes: int = 1_048_576,
    ):
        if response_timeout_seconds <= 0:
            raise ValueError('response_timeout_seconds must be positive')
        if max_response_bytes <= 0:
            raise ValueError('max_response_bytes must be positive')
        self._node_binary = node_binary
        self._worker_path = worker_path or Path(__file__).resolve().parents[4] / "nodejs" / "legado_js_worker.js"
        self._bridge_http_handler = bridge_http_handler
        self._response_timeout_seconds = response_timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout_buffer = bytearray()
        self._execution_deadline: float | None = None

    def set_execution_deadline(self, deadline: float | None) -> None:
        self._execution_deadline = deadline

    def _ensure_started(self) -> None:
        if self._process and self._process.poll() is None:
            return

        self._process = subprocess.Popen(
            [self._node_binary, str(self._worker_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._stdout_buffer.clear()

    def execute(self, code: str, context: JsExecutionContext) -> JsWorkerOutput:
        started_at = time.time()
        now = time.monotonic()
        if self._execution_deadline is not None and self._execution_deadline <= now:
            self._terminate_process()
            return self._failed_output(context, code, started_at, 'EXECUTION_TIMEOUT')
        self._ensure_started()
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
                (json.dumps(payload, ensure_ascii=False, default=self._json_default) + "\n").encode('utf-8')
            )
            self._process.stdin.flush()
        except (BrokenPipeError, OSError):
            return self._failed_output(context, code, started_at, 'WORKER_IO_ERROR')

        deadline = time.monotonic() + self._response_timeout_seconds
        if self._execution_deadline is not None:
            deadline = min(deadline, self._execution_deadline)
        while True:
            raw, read_error = self._read_response_line(deadline)
            if read_error:
                if read_error in {'EXECUTION_TIMEOUT', 'RESPONSE_TOO_LARGE'}:
                    self._terminate_process()
                return self._failed_output(context, code, started_at, read_error)
            try:
                message = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._failed_output(context, code, started_at, 'MALFORMED_RESPONSE')
            if not isinstance(message, dict):
                return self._failed_output(context, code, started_at, 'MALFORMED_RESPONSE')
            if message.get("type") == "bridge_http":
                if not isinstance(message.get('request'), dict) or not message.get('id'):
                    return self._bridge_failure_output(context, code, started_at, 'MALFORMED_RESPONSE')
                response, bridge_error = self._bridge_response(message['request'], deadline)
                if bridge_error == 'EXECUTION_TIMEOUT':
                    return self._timeout_output(context, code, started_at)
                if bridge_error:
                    return self._bridge_failure_output(context, code, started_at, bridge_error)
                try:
                    self._process.stdin.write(
                        (
                            json.dumps(
                                {
                                    "type": "bridge_http_result",
                                    "id": message["id"],
                                    "response": response,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        ).encode('utf-8')
                    )
                    self._process.stdin.flush()
                except (BrokenPipeError, OSError, KeyError):
                    return self._bridge_failure_output(context, code, started_at, 'WORKER_IO_ERROR')
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

    def _bridge_response(self, request: dict, deadline: float) -> tuple[dict | None, str | None]:
        if self._bridge_http_handler is None:
            return {'status': 500, 'text': 'bridge handler missing', 'headers': {}}, None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, 'EXECUTION_TIMEOUT'
        # Timed-out synchronous callbacks cannot be killed safely. Keep them bounded globally
        # by retaining a semaphore slot until the callback actually returns.
        if not _BRIDGE_CALLBACK_SLOTS.acquire(blocking=False):
            return None, 'BRIDGE_CAPACITY_EXHAUSTED'
        future = _BRIDGE_CALLBACK_EXECUTOR.submit(
            _bridge_callback_target,
            self._bridge_http_handler,
            request,
        )
        try:
            response = future.result(timeout=remaining)
            if not isinstance(response, dict):
                return None, 'WORKER_IO_ERROR'
            return response, None
        except TimeoutError:
            return None, 'EXECUTION_TIMEOUT'
        except Exception:
            return None, 'WORKER_IO_ERROR'

    def close(self) -> None:
        self._terminate_process()

    def _timeout_output(self, context: JsExecutionContext, code: str, started_at: float) -> JsWorkerOutput:
        self._terminate_process()
        return self._failed_output(context, code, started_at, 'EXECUTION_TIMEOUT')

    def _bridge_failure_output(
        self,
        context: JsExecutionContext,
        code: str,
        started_at: float,
        error_code: str,
    ) -> JsWorkerOutput:
        self._terminate_process()
        return self._failed_output(context, code, started_at, error_code)

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

    def _read_response_line(self, deadline: float) -> tuple[bytes | None, str | None]:
        assert self._process is not None
        assert self._process.stdout is not None
        stdout = self._process.stdout
        while True:
            newline_index = self._stdout_buffer.find(b'\n')
            if newline_index >= 0:
                if newline_index > self._max_response_bytes:
                    return None, 'RESPONSE_TOO_LARGE'
                line = bytes(self._stdout_buffer[:newline_index])
                del self._stdout_buffer[:newline_index + 1]
                return line, None
            if len(self._stdout_buffer) > self._max_response_bytes:
                return None, 'RESPONSE_TOO_LARGE'
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, 'EXECUTION_TIMEOUT'
            try:
                ready, _, _ = select.select([stdout], [], [], remaining)
            except (OSError, ValueError):
                return None, 'WORKER_IO_ERROR'
            if not ready:
                return None, 'EXECUTION_TIMEOUT'
            try:
                chunk = os.read(stdout.fileno(), 65_536)
            except OSError:
                return None, 'WORKER_IO_ERROR'
            if not chunk:
                return None, 'WORKER_EOF'
            self._stdout_buffer.extend(chunk)

    def _terminate_process(self) -> None:
        process = self._process
        self._process = None
        self._stdout_buffer.clear()
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=self.PROCESS_TERMINATE_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=self.PROCESS_TERMINATE_WAIT_SECONDS)

    @staticmethod
    def _json_default(value):
        if isinstance(value, etree._Element):
            return etree.tostring(value, encoding='unicode', method='html')
        return str(value)
