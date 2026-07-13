from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.legado.engine.js_session_models import JsExecutionContext


@dataclass
class LegadoJsCompatProfile:
    mode: str = "native"
    strict: bool = False
    allowed_stages: tuple[str, ...] = (
        "search_url_js",
        "search_rule_js",
        "book_info_init",
        "toc_rule_js",
        "content_rule_js",
    )
    default_variables: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def native_defaults(cls) -> "LegadoJsCompatProfile":
        return cls(
            mode="native",
            strict=False,
            default_variables={
                "page": 1,
                "keyword": "",
                "key": "",
                "searchKey": "",
            },
        )

    def build_context(
        self,
        stage: str,
        source: dict[str, Any] | None = None,
        book: dict[str, Any] | None = None,
        result: Any = None,
        base_url: str = "",
        cache: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> JsExecutionContext:
        if stage not in self.allowed_stages:
            raise ValueError(f"unsupported js stage: {stage}")

        merged_variables = dict(self.default_variables)
        merged_variables.update(variables or {})

        return JsExecutionContext(
            stage=stage,
            source=dict(source or {}),
            book=dict(book or {}),
            result=result,
            base_url=base_url,
            cache=dict(cache or {}),
            variables=merged_variables,
            headers=dict(headers or {}),
        )
