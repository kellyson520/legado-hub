from __future__ import annotations

import logging
import os
from typing import Any

from .native_models import RuntimeResult
from .native_runtime_client import NativeRuntimeClient
from .runtime_diff import compare_runtime_results

logger = logging.getLogger("legado_runtime_facade")

MIGRATION_GATE = {
    "unexplained_diffs": 0,
    "golden_cases": 100,
    "real_source_runs": 20,
    "fallback_rate": 0.0,
}


def migration_gate_passed(
    *,
    unexplained_diffs: int,
    golden_cases: int,
    real_source_runs: int,
    fallback_rate: float,
) -> bool:
    return (
        unexplained_diffs <= MIGRATION_GATE["unexplained_diffs"]
        and golden_cases >= MIGRATION_GATE["golden_cases"]
        and real_source_runs >= MIGRATION_GATE["real_source_runs"]
        and fallback_rate <= MIGRATION_GATE["fallback_rate"]
    )


class PythonRuntimeFallback:
    def extract(
        self,
        content: Any,
        rule: str,
        *,
        operation: str,
        base_url: str = "",
        is_html: bool = False,
        context: dict[str, Any] | None = None,
        **_: Any,
    ) -> RuntimeResult:
        from .rule_selector import RuleSelector

        result = RuleSelector.extract(
            content,
            rule,
            base_url=base_url,
            is_html=is_html,
            context={
                key: value
                for key, value in (context or {}).items()
                if key not in {"runtime_facade", "_skip_runtime_facade"}
            },
            as_list=operation in {"extract_list", "extract_elements"},
        )
        value = result.value
        if operation in {"extract_list", "extract_elements"} and value is not None and not isinstance(value, list):
            value = [value]
        return RuntimeResult(
            success=result.success,
            value=value,
            value_type="list" if isinstance(value, list) else "string",
            trace={"engine": "python-fallback", "rule_type": result.rule_type},
        )

    def resolve_url(self, rule_url: str, base_url: str, redirect_url: str = "", **_: Any) -> RuntimeResult:
        from .url_utils import UrlUtils

        return RuntimeResult(
            success=True,
            value=UrlUtils.resolve_relative(rule_url, redirect_url or base_url),
            value_type="string",
            trace={"engine": "python-fallback"},
        )


class LegadoRuntimeFacade:
    FALLBACK_ERROR_CODES = {
        "RUNTIME_UNAVAILABLE",
        "WORKER_EOF",
        "WORKER_IO_ERROR",
        "EXECUTION_TIMEOUT",
        "BRIDGE_TIMEOUT",
        "MALFORMED_RESPONSE",
        "MISMATCHED_RESPONSE_ID",
    }

    def __init__(
        self,
        native_client: NativeRuntimeClient | Any | None = None,
        fallback: PythonRuntimeFallback | Any | None = None,
        *,
        mode: str | None = None,
        timeout: float = 10.0,
        bridge_handler=None,
    ):
        self.native_client = native_client or NativeRuntimeClient(
            response_timeout=timeout,
            bridge_handler=bridge_handler,
        )
        self.fallback = fallback or PythonRuntimeFallback()
        self.mode = mode or os.getenv("LEGADO_RUNTIME_MODE", "python_primary")
        self.timeout = timeout
        self._session: dict[str, Any] = {}
        self.diffs: list[dict[str, Any]] = []
        self.module_modes: dict[str, str] = {}
        if self.mode not in {"native_kotlin", "python_shadow", "python_primary"}:
            raise ValueError(f"unsupported LEGADO_RUNTIME_MODE: {self.mode}")

    def set_module_mode(self, module: str, mode: str, evidence: dict[str, Any] | None = None) -> None:
        if mode not in {"native_kotlin", "python_shadow", "python_primary"}:
            raise ValueError(f"unsupported module runtime mode: {mode}")
        evidence = evidence or {}
        if mode == "python_primary" and not migration_gate_passed(
            unexplained_diffs=int(evidence.get("unexplained_diffs", 0)),
            golden_cases=int(evidence.get("golden_cases", 0)),
            real_source_runs=int(evidence.get("real_source_runs", 0)),
            fallback_rate=float(evidence.get("fallback_rate", 1.0)),
        ):
            raise ValueError(f"migration gate not passed for module: {module}")
        self.module_modes[module] = mode

    def begin_session(self, **context: Any) -> dict[str, Any]:
        self._session = dict(context)
        return self._session

    def end_session(self) -> None:
        self._session = {}

    def extract(
        self,
        content: Any,
        rule: str,
        *,
        operation: str = "extract_string",
        stage: str = "",
        base_url: str = "",
        redirect_url: str = "",
        context: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> RuntimeResult:
        payload = {
            "stage": stage,
            "rule": rule,
            "content": content,
            "content_type": "html" if isinstance(content, str) else "json",
            "base_url": base_url,
            "redirect_url": redirect_url,
            "context": context or self._session,
        }
        if self.mode == "python_primary":
            return self.fallback.extract(
                content,
                rule,
                operation=operation,
                base_url=base_url,
                is_html=isinstance(content, str),
                context=context or self._session,
                stage=stage,
            )

        native_result = self.native_client.call(operation, payload, timeout or self.timeout)
        if self.mode == "python_shadow":
            fallback_result = self.fallback.extract(
                content,
                rule,
                operation=operation,
                base_url=base_url,
                is_html=isinstance(content, str),
                context=context or self._session,
                stage=stage,
            )
            diff = compare_runtime_results(native_result, fallback_result)
            if diff["code"] != "OK":
                self.diffs.append(
                    {
                        "stage": stage,
                        "rule_preview": rule[:120],
                        "native_value": native_result.value,
                        "python_value": fallback_result.value,
                        **diff,
                    }
                )
                logger.warning(
                    "native semantics diff stage=%s rule=%s native=%r fallback=%r",
                    stage,
                    rule[:120],
                    native_result.value,
                    fallback_result.value,
                )
            return native_result

        if native_result.success:
            return native_result
        if native_result.error_code in self.FALLBACK_ERROR_CODES:
            fallback_result = self.fallback.extract(
                content,
                rule,
                operation=operation,
                base_url=base_url,
                is_html=isinstance(content, str),
                context=context or self._session,
                stage=stage,
            )
            fallback_result.trace.setdefault("fallback_reason", native_result.error_code)
            return fallback_result
        return native_result

    def resolve_url(
        self,
        rule_url: str,
        *,
        base_url: str = "",
        redirect_url: str = "",
        stage: str = "",
        timeout: float | None = None,
    ) -> RuntimeResult:
        if self.mode == "python_primary":
            return self.fallback.resolve_url(rule_url, base_url, redirect_url, stage=stage)
        native_result = self.native_client.call(
            "resolve_url",
            {
                "stage": stage,
                "rule": rule_url,
                "content": "",
                "base_url": base_url,
                "redirect_url": redirect_url,
            },
            timeout or self.timeout,
        )
        if native_result.success or self.mode == "python_shadow":
            return native_result
        if native_result.error_code in self.FALLBACK_ERROR_CODES:
            fallback_result = self.fallback.resolve_url(rule_url, base_url, redirect_url, stage=stage)
            fallback_result.trace.setdefault("fallback_reason", native_result.error_code)
            return fallback_result
        return native_result

    def close(self) -> None:
        close = getattr(self.native_client, "close", None)
        if callable(close):
            close()
