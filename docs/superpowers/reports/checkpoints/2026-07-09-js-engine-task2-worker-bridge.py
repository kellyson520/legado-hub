from __future__ import annotations

import json
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
    ):
        self._node_binary = node_binary
        self._worker_path = worker_path or Path(__file__).resolve().parents[4] / "nodejs" / "legado_js_worker.js"
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

        self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._process.stdin.flush()

        raw = self._process.stdout.readline()
        message = json.loads(raw)
        elapsed_ms = int((time.time() - started_at) * 1000)
        trace = JsExecutionTrace(
            stage=context.stage,
            success=bool(message.get("success")),
            rule_preview=code[:120],
            worker_elapsed_ms=elapsed_ms,
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
        if self._process and self._process.poll() is None:
            self._process.terminate()
