from __future__ import annotations

import json
import logging
import os
import select
import shlex
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from .native_models import RuntimeResult

logger = logging.getLogger("legado_native_runtime")


class NativeRuntimeClient:
    """Owns one long-lived headless Kotlin runtime process."""

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        response_timeout: float = 10.0,
        max_response_bytes: int = 4 * 1024 * 1024,
        process_factory=subprocess.Popen,
    ):
        self.command = list(command or self._default_command())
        self.response_timeout = response_timeout
        self.max_response_bytes = max_response_bytes
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

    def call(self, operation: str, payload: dict[str, Any], timeout: float | None = None) -> RuntimeResult:
        with self._lock:
            process = self._ensure_process()
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
                raw = self._readline(process, timeout if timeout is not None else self.response_timeout)
            except (BrokenPipeError, OSError):
                self._restart_after_failure()
                return self._failed("WORKER_IO_ERROR", "native runtime pipe failed")

            if raw is None:
                self._restart_after_failure()
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
            if response.get("id") != request_id:
                self._restart_after_failure()
                return self._failed("MISMATCHED_RESPONSE_ID", "native runtime response id did not match request")
            return RuntimeResult.from_payload(response)

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
        for raw_line in iter(process.stderr.readline, b""):
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if line:
                self._stderr_lines.append(line)
                logger.debug("native runtime: %s", line)

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
