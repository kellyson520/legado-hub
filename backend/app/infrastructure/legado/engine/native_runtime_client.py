from __future__ import annotations

import json
import os
import select
import shlex
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from .native_models import RuntimeResult
from app.core.logging import get_logger

logger = get_logger("legado_native_runtime")
_BRIDGE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="legado-native-bridge")


class NativeRuntimeClient:
    """Owns one long-lived headless Kotlin runtime process."""

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        response_timeout: float = 10.0,
        max_response_bytes: int = 4 * 1024 * 1024,
        bridge_handler=None,
        cache_handler=None,
        process_factory=subprocess.Popen,
    ):
        self.command = list(command or self._default_command())
        self.response_timeout = response_timeout
        self.max_response_bytes = max_response_bytes
        self.bridge_handler = bridge_handler
        self.cache_handler = cache_handler
        self._process_factory = process_factory
        self._process: subprocess.Popen[bytes] | None = None
        self._stderr_lines: deque[str] = deque(maxlen=200)
        self._stderr_thread: threading.Thread | None = None
        self.restart_count = 0
        self._lock = threading.RLock()

    @staticmethod
    def _default_command() -> list[str]:
        configured = os.getenv("LEGADO_RUNTIME_COMMAND", "").strip()
        if configured:
            return shlex.split(configured)
        configured_jar = os.getenv("LEGADO_RUNTIME_JAR", "/app/runtime/legado-runtime.jar")
        return ["java", "-jar", configured_jar]

    def ping(self) -> RuntimeResult:
        return self.call("ping", {}, timeout=self.response_timeout)

    def capabilities(self) -> RuntimeResult:
        return self.call("capabilities", {}, timeout=self.response_timeout)

    def call(
        self,
        operation: str,
        payload: dict[str, Any],
        timeout: float | None = None,
        *,
        _retry_after_eof: bool = True,
    ) -> RuntimeResult:
        with self._lock:
            try:
                process = self._ensure_process()
            except RuntimeError as exc:
                return self._failed("RUNTIME_UNAVAILABLE", str(exc))
            request_id = uuid4().hex
            request = {
                "id": request_id,
                "protocol_version": 1,
                "op": operation,
                **payload,
            }
            try:
                assert process.stdin is not None
                process.stdin.write((json.dumps(request, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
                process.stdin.flush()
                deadline = time.monotonic() + (timeout if timeout is not None else self.response_timeout)
                while True:
                    remaining = deadline - time.monotonic()
                    raw = self._readline(process, remaining)
                    if raw is None:
                        process_was_dead = process.poll() is not None
                        self._restart_after_failure()
                        if _retry_after_eof and process_was_dead:
                            return self.call(operation, payload, timeout, _retry_after_eof=False)
                        return self._failed("EXECUTION_TIMEOUT", "native runtime response timed out")
                    if len(raw) > self.max_response_bytes:
                        self._restart_after_failure()
                        return self._failed("RESPONSE_TOO_LARGE", "native runtime response exceeded the limit")
                    try:
                        response = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        self._restart_after_failure()
                        return self._failed("MALFORMED_RESPONSE", "native runtime returned invalid JSON")
                    if not isinstance(response, dict):
                        self._restart_after_failure()
                        return self._failed("MALFORMED_RESPONSE", "native runtime returned a non-object response")
                    message_type = response.get("type")
                    if message_type == "bridge_http":
                        bridge_result = self._run_bridge(response, deadline)
                        result_type = "bridge_http_result"
                    elif message_type == "bridge_cache":
                        bridge_result = self._run_cache(response, deadline)
                        result_type = "bridge_cache_result"
                    else:
                        break
                    if bridge_result is None:
                        self._restart_after_failure()
                        return self._failed(
                            "CACHE_TIMEOUT" if message_type == "bridge_cache" else "BRIDGE_TIMEOUT",
                            "native runtime bridge request timed out",
                        )
                    try:
                        self._write_json(
                            process,
                            {
                                "type": result_type,
                                "id": response.get("id"),
                                "response": bridge_result,
                            },
                        )
                    except (BrokenPipeError, OSError):
                        self._restart_after_failure()
                        return self._failed("WORKER_IO_ERROR", "native runtime bridge pipe failed")
            except (BrokenPipeError, OSError):
                self._restart_after_failure()
                return self._failed("WORKER_IO_ERROR", "native runtime pipe failed")
            if response.get("id") != request_id:
                self._restart_after_failure()
                return self._failed("MISMATCHED_RESPONSE_ID", "native runtime response id did not match request")
            return RuntimeResult.from_payload(response)

    def _run_bridge(self, message: dict[str, Any], deadline: float) -> dict[str, Any] | None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        request = message.get("request")
        if not isinstance(request, dict):
            return {"status": 400, "text": "malformed bridge request", "headers": {}, "error_code": "MALFORMED_BRIDGE_REQUEST"}
        if self.bridge_handler is None:
            return {"status": 503, "text": "native runtime bridge unavailable", "headers": {}, "error_code": "BRIDGE_UNAVAILABLE"}
        future = _BRIDGE_EXECUTOR.submit(self.bridge_handler, request)
        try:
            result = future.result(timeout=remaining)
        except FutureTimeoutError:
            return None
        except Exception as exc:  # noqa: BLE001 - bridge errors are part of the protocol
            return {"status": 599, "text": str(exc), "headers": {}, "error_code": "BRIDGE_ERROR"}
        return result if isinstance(result, dict) else {"status": 599, "text": "bridge returned non-object", "headers": {}, "error_code": "BRIDGE_ERROR"}

    def _run_cache(self, message: dict[str, Any], deadline: float) -> dict[str, Any] | None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        request = message.get("request")
        if not isinstance(request, dict):
            return {"found": False, "error_code": "MALFORMED_CACHE_REQUEST"}
        if self.cache_handler is None:
            return {"found": False, "error_code": "CACHE_BRIDGE_UNAVAILABLE"}
        future = _BRIDGE_EXECUTOR.submit(self.cache_handler, request)
        try:
            result = future.result(timeout=remaining)
        except FutureTimeoutError:
            return None
        except Exception as exc:  # noqa: BLE001 - converted to a stable protocol error
            return {"found": False, "error_code": "CACHE_BRIDGE_ERROR", "message": str(exc)}
        return result if isinstance(result, dict) else {"found": False, "error_code": "CACHE_BRIDGE_ERROR"}

    @staticmethod
    def _write_json(process: subprocess.Popen[bytes], payload: dict[str, Any]) -> None:
        assert process.stdin is not None
        process.stdin.write((json.dumps(payload, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
        process.stdin.flush()

    def close(self) -> None:
        with self._lock:
            self._terminate_process()

    def _ensure_process(self) -> subprocess.Popen[bytes]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        if self._process is not None:
            self.restart_count += 1
            self._terminate_process()
        try:
            process = self._process_factory(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"native runtime unavailable: {exc}") from exc
        self._process = process
        self._stderr_thread = threading.Thread(target=self._drain_stderr, args=(process,), daemon=True)
        self._stderr_thread.start()
        return process

    def _readline(self, process: subprocess.Popen[bytes], timeout: float) -> bytes | None:
        assert process.stdout is not None
        deadline = time.monotonic() + max(timeout, 0.01)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([process.stdout], [], [], remaining)
            if not ready:
                return None
            line = process.stdout.readline()
            if not line:
                return None
            return line.rstrip(b"\r\n")

    def _drain_stderr(self, process: subprocess.Popen[bytes]) -> None:
        if process.stderr is None:
            return
        try:
            for raw_line in iter(process.stderr.readline, b""):
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._stderr_lines.append(line)
                    logger.debug("native runtime: %s", line)
        except (OSError, ValueError):
            # Closing a subprocess stream while the daemon drain thread is
            # blocked is an expected shutdown path, not a runtime failure.
            return

    def _restart_after_failure(self) -> None:
        self.restart_count += 1
        self._terminate_process()

    def _terminate_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    @staticmethod
    def _failed(code: str, message: str) -> RuntimeResult:
        return RuntimeResult(success=False, error_code=code, error=message, trace={"engine": "python-client"})
