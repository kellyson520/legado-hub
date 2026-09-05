from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup, Tag
from lxml import etree

from app.infrastructure.legado.engine.jsonpath_ext import JsonPathExt
from app.infrastructure.legado.engine.js_runtime import JsRuntime
from app.infrastructure.legado.engine.url_utils import UrlUtils


class RuleType:
    AUTO = "auto"
    JSONPATH = "jsonpath"
    CSS = "css"
    XPATH = "xpath"
    JS = "js"
    STRING = "string"
    NONE = "none"


@dataclass
class SelectorResult:
    value: Any = None
    success: bool = False
    rule_type: str = RuleType.NONE

    def is_empty(self) -> bool:
        if self.value is None:
            return True
        if isinstance(self.value, str):
            return self.value.strip() == ""
        if isinstance(self.value, (list, tuple, set, dict)):
            return len(self.value) == 0
        return False


class RuleSelector:
    _VALUE_ACCESSORS = {
        "text",
        "html",
        "textnodes",
        "outerhtml",
        "href",
        "src",
        "title",
        "value",
        "alt",
    }

    @classmethod
    def extract(
        cls,
        data: Any,
        rule: str,
        base_url: str = "",
        is_html: bool = False,
        context: dict[str, Any] | None = None,
        as_list: bool = False,
    ) -> SelectorResult:
        if not rule:
            return SelectorResult()

        context = context or {}
        runtime_facade = context.get("runtime_facade")
        if runtime_facade is not None and not context.get("_skip_runtime_facade"):
            delegated_context = {
                key: value
                for key, value in context.items()
                if key not in {"runtime_facade", "_skip_runtime_facade"}
            }
            delegated = runtime_facade.extract(
                data,
                rule,
                operation="extract_list" if as_list else "extract_string",
                stage=str(context.get("stage", "selector")),
                base_url=base_url,
                context=delegated_context,
            )
            return SelectorResult(
                value=delegated.value,
                success=delegated.success,
                rule_type=RuleType.AUTO,
            )
        last_result = SelectorResult(rule_type=RuleType.NONE)

        for alternative in JsonPathExt._split_top_level(rule.strip(), "||"):
            alternative = alternative.strip()
            if not alternative:
                continue

            candidate = cls._extract_single(
                data=data,
                rule=alternative,
                base_url=base_url,
                is_html=is_html,
                context=context,
                as_list=as_list,
            )
            last_result = candidate
            if candidate.success and not candidate.is_empty():
                return candidate

        return last_result

    @classmethod
    def extract_list(
        cls,
        data: Any,
        rule: str,
        base_url: str = "",
        is_html: bool = False,
        context: dict[str, Any] | None = None,
    ) -> list[Any]:
        result = cls.extract(
            data=data,
            rule=rule,
            base_url=base_url,
            is_html=is_html,
            context=context,
            as_list=True,
        )
        if not result.success or result.value is None:
            return []
        if isinstance(result.value, list):
            return result.value
        return [result.value]

    @classmethod
    def _extract_single(
        cls,
        data: Any,
        rule: str,
        base_url: str,
        is_html: bool,
        context: dict[str, Any],
        as_list: bool,
    ) -> SelectorResult:
        inline_result = cls._extract_with_inline_js(
            data=data,
            rule=rule,
            base_url=base_url,
            is_html=is_html,
            context=context,
            as_list=as_list,
        )
        if inline_result is not None:
            return inline_result

        base_rule, post_ops = JsonPathExt._split_post_ops(rule)
        base_rule = base_rule.strip()
        rule_type = cls._parse_rule_type(base_rule, data, is_html)

        if rule_type == RuleType.JS:
            js_code = cls._strip_js_wrapper(base_rule)
            value = cls._get_js_runtime(context).execute(
                js_code,
                data,
                result=data,
                baseUrl=base_url,
                **context,
            )
            value = cls._apply_post_ops(value, post_ops)
            value = cls._maybe_complete_url(value, base_rule, base_url)
            return SelectorResult(value=value, success=value is not None, rule_type=rule_type)

        if rule_type == RuleType.JSONPATH:
            value = JsonPathExt.query(data, base_rule)
            value = cls._apply_post_ops(value, post_ops)
            value = cls._maybe_complete_url(value, base_rule, base_url)
            return SelectorResult(value=value, success=value is not None, rule_type=rule_type)

        if rule_type == RuleType.XPATH:
            value = cls._extract_xpath(data, base_rule, as_list=as_list)
            value = cls._apply_post_ops(value, post_ops)
            value = cls._maybe_complete_url(value, base_rule, base_url)
            return SelectorResult(value=value, success=value is not None, rule_type=rule_type)

        if rule_type == RuleType.CSS:
            value = cls._extract_css(data, base_rule, as_list=as_list)
            value = cls._apply_post_ops(value, post_ops)
            value = cls._maybe_complete_url(value, base_rule, base_url)
            return SelectorResult(value=value, success=value is not None, rule_type=rule_type)

        if rule_type == RuleType.STRING:
            value = cls._extract_string(data, base_rule, base_url)
            value = cls._apply_post_ops(value, post_ops)
            value = cls._maybe_complete_url(value, base_rule, base_url)
            return SelectorResult(value=value, success=value is not None, rule_type=rule_type)

        return SelectorResult(value=None, success=False, rule_type=RuleType.NONE)

    @classmethod
    def _extract_with_inline_js(
        cls,
        data: Any,
        rule: str,
        base_url: str,
        is_html: bool,
        context: dict[str, Any],
        as_list: bool,
    ) -> SelectorResult | None:
        js_markers = ("\n@js:", "@js:", "\n<js>", "<js>")
        marker_index = -1
        marker = ""
        for candidate in js_markers:
            idx = rule.find(candidate)
            if idx > 0 and (marker_index < 0 or idx < marker_index):
                marker_index = idx
                marker = candidate

        if marker_index < 0:
            return None

        pre_rule = rule[:marker_index].strip()
        js_code = rule[marker_index + len(marker) :].strip()
        if js_code.endswith("</js>"):
            js_code = js_code[:-5].strip()

        if pre_rule:
            pre_result = cls._extract_single(
                data=data,
                rule=pre_rule,
                base_url=base_url,
                is_html=is_html,
                context=context,
                as_list=as_list,
            )
            result_value = pre_result.value
        else:
            result_value = data

        # The JSONPath expression before inline JS is evaluated against the
        # current item, but templates inside the JS block still refer to that
        # original item (`{{$.id}}`, `{{$.blogId}}`, ...). Render them before
        # handing the code to the JS runtime; passing only `result_value`
        # would lose fields when the pre-rule resolves to an empty value.
        if isinstance(data, (dict, list)) and "{{" in js_code and "}}" in js_code:
            js_code = JsonPathExt.fill_template(
                js_code,
                data,
                extra_vars={
                    "baseUrl": base_url,
                    "result": result_value,
                    "cache": context.get("cache", {}),
                },
            )

        value = cls._get_js_runtime(context).execute(
            js_code,
            result_value,
            result=result_value,
            baseUrl=base_url,
            **context,
        )
        value = cls._maybe_complete_url(value, rule, base_url)
        return SelectorResult(value=value, success=value is not None, rule_type=RuleType.JS)

    @classmethod
    def _parse_rule_type(cls, rule: str, data: Any, is_html: bool) -> str:
        rule_lower = rule.lower()
        if not rule:
            return RuleType.NONE
        if rule_lower.startswith("@js:") or rule_lower.startswith("<js>"):
            return RuleType.JS
        if rule_lower.startswith("@css:") or rule_lower.startswith("css:"):
            return RuleType.CSS
        if rule.startswith("$"):
            return RuleType.JSONPATH
        if cls._looks_like_template(rule):
            return RuleType.STRING
        if rule.startswith("@XPath:") or rule_lower.startswith("xpath:"):
            return RuleType.XPATH
        if cls._looks_like_xpath(rule):
            return RuleType.XPATH
        if isinstance(data, (dict, list)):
            return RuleType.JSONPATH
        if is_html or cls._looks_like_html_selector(rule, data):
            return RuleType.CSS
        return RuleType.STRING

    @classmethod
    def _extract_string(cls, data: Any, rule: str, base_url: str) -> Any:
        if cls._looks_like_template(rule):
            return JsonPathExt.fill_template(
                rule,
                data,
                extra_vars={
                    "result": data,
                    "baseUrl": base_url,
                },
            )

        if isinstance(data, (dict, list)):
            value = JsonPathExt.query(data, rule)
            if value is not None:
                return value

        return rule

    @classmethod
    def _extract_xpath(cls, data: Any, rule: str, as_list: bool) -> Any:
        expression = rule
        if rule.startswith("@XPath:"):
            expression = rule[7:]
        elif rule.lower().startswith("xpath:"):
            expression = rule[6:]
        root = cls._to_xpath_root(data)
        if root is None:
            return None

        try:
            result = root.xpath(expression)
        except Exception:
            return None

        if as_list:
            return result

        if len(result) == 1:
            single = result[0]
            if isinstance(single, etree._Element):
                return single
            return single

        return result

    @classmethod
    def _extract_css(cls, data: Any, rule: str, as_list: bool) -> Any:
        if rule.lower().startswith("@css:"):
            rule = rule[5:].strip()
        elif rule.lower().startswith("css:"):
            rule = rule[4:].strip()

        current_nodes = cls._coerce_html_nodes(data)
        if not current_nodes:
            return None

        if rule.lower() in cls._VALUE_ACCESSORS:
            return cls._extract_from_nodes(current_nodes, rule, as_list=as_list)

        parts = [part.strip() for part in rule.split("@") if part.strip()]
        if not parts:
            return None

        terminal: str | None = None
        for part in parts:
            if part.lower() in cls._VALUE_ACCESSORS:
                terminal = part
                break
            current_nodes = cls._select_on_nodes(current_nodes, part)
            if not current_nodes:
                return None

        if terminal is not None:
            return cls._extract_from_nodes(current_nodes, terminal, as_list=as_list)

        if as_list:
            return current_nodes

        return cls._extract_from_nodes(current_nodes, "text", as_list=as_list)

    @classmethod
    def _coerce_html_nodes(cls, data: Any) -> list[Any]:
        if isinstance(data, list):
            nodes: list[Any] = []
            for item in data:
                nodes.extend(cls._coerce_html_nodes(item))
            return nodes

        if isinstance(data, Tag):
            return [data]

        if isinstance(data, BeautifulSoup):
            return [data]

        if isinstance(data, etree._Element):
            return [data]

        if isinstance(data, str):
            return [BeautifulSoup(data, "lxml")]

        return []

    @classmethod
    def _select_on_nodes(cls, nodes: list[Any], segment: str) -> list[Any]:
        if not nodes:
            return []

        selected: list[Any] = []
        selector, index, exclude = cls._parse_css_segment(segment)

        for node in nodes:
            if segment.startswith("text."):
                matched = cls._find_by_text(node, segment[5:])
            else:
                matched = cls._select_css(node, selector)

            if index is not None:
                picked = cls._pick_index(matched, index)
                matched = [picked] if picked is not None else []

            selected.extend(matched)

        if exclude:
            selected = [
                node
                for idx, node in enumerate(selected)
                if idx not in exclude and idx - len(selected) not in exclude
            ]

        return selected

    @classmethod
    def _parse_css_segment(cls, segment: str) -> tuple[str, int | None, set[int]]:
        exclude: set[int] = set()
        selector_part = segment.strip()

        if "!" in selector_part:
            selector_part, exclude_part = selector_part.split("!", 1)
            for raw in exclude_part.split(":"):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    exclude.add(int(raw))
                except ValueError:
                    continue

        selector_part = selector_part.strip()

        match = re.match(r"^(?P<selector>.+?)\.(?P<index>-?\d+)$", selector_part)
        index = None
        if match and not selector_part.startswith((".", "#")):
            selector_part = match.group("selector")
            index = int(match.group("index"))
        elif selector_part.startswith("tag."):
            tag_match = re.match(r"^tag\.(?P<tag>[a-zA-Z0-9_-]+)\.(?P<index>-?\d+)$", selector_part)
            if tag_match:
                selector_part = f"tag.{tag_match.group('tag')}"
                index = int(tag_match.group("index"))

        return cls._normalize_selector(selector_part), index, exclude

    @classmethod
    def _normalize_selector(cls, selector: str) -> str:
        selector = selector.strip()
        if not selector:
            return selector
        if selector.startswith("class."):
            classes = selector[6:].strip().split()
            return "".join(f".{name}" for name in classes if name)
        if selector.startswith("id."):
            return f"#{selector[3:].strip()}"
        if selector.startswith("tag."):
            return selector[4:].strip()
        return selector

    @classmethod
    def _select_css(cls, node: Any, selector: str) -> list[Any]:
        if not selector:
            return []

        if isinstance(node, etree._Element):
            html = etree.tostring(node, encoding="unicode")
            node = BeautifulSoup(html, "lxml")

        if isinstance(node, str):
            node = BeautifulSoup(node, "lxml")

        if isinstance(node, (BeautifulSoup, Tag)):
            try:
                return [item for item in node.select(selector) if isinstance(item, Tag)]
            except Exception:
                return []

        return []

    @classmethod
    def _find_by_text(cls, node: Any, text: str) -> list[Any]:
        if isinstance(node, etree._Element):
            html = etree.tostring(node, encoding="unicode")
            node = BeautifulSoup(html, "lxml")

        if isinstance(node, str):
            node = BeautifulSoup(node, "lxml")

        if not isinstance(node, (BeautifulSoup, Tag)):
            return []

        results = []
        for item in node.find_all(True):
            if text in item.get_text(" ", strip=True):
                results.append(item)
        return results

    @classmethod
    def _extract_from_nodes(cls, nodes: list[Any], accessor: str, as_list: bool) -> Any:
        key = accessor.lower()
        if key == "text":
            values = [cls._node_text(node) for node in nodes]
        elif key == "html":
            values = [cls._node_inner_html(node) for node in nodes]
        elif key == "outerhtml":
            values = [cls._node_outer_html(node) for node in nodes]
        elif key == "textnodes":
            values = []
            for node in nodes:
                values.extend(cls._node_text_nodes(node))
        else:
            values = [cls._node_attr(node, accessor) for node in nodes]

        values = [value for value in values if value not in (None, "")]
        if as_list:
            return values
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        return values

    @classmethod
    def _node_text(cls, node: Any) -> str:
        if isinstance(node, etree._Element):
            return "".join(node.itertext()).strip()
        if isinstance(node, Tag):
            return node.get_text(strip=True)
        return str(node).strip()

    @classmethod
    def _node_inner_html(cls, node: Any) -> str:
        if isinstance(node, etree._Element):
            return "".join(
                etree.tostring(child, encoding="unicode")
                for child in node.iterchildren()
            ).strip()
        if isinstance(node, Tag):
            return "".join(str(child) for child in node.contents).strip()
        return str(node).strip()

    @classmethod
    def _node_outer_html(cls, node: Any) -> str:
        if isinstance(node, etree._Element):
            return etree.tostring(node, encoding="unicode").strip()
        if isinstance(node, Tag):
            return str(node).strip()
        return str(node).strip()

    @classmethod
    def _node_text_nodes(cls, node: Any) -> list[str]:
        if isinstance(node, etree._Element):
            return [text.strip() for text in node.itertext() if text and text.strip()]
        if isinstance(node, Tag):
            return [text.strip() for text in node.stripped_strings if text.strip()]
        text = str(node).strip()
        return [text] if text else []

    @classmethod
    def _node_attr(cls, node: Any, attr_name: str) -> str | None:
        if isinstance(node, etree._Element):
            return node.get(attr_name)
        if isinstance(node, Tag):
            value = node.get(attr_name)
            return value if value is not None else None
        return None

    @staticmethod
    def _pick_index(values: list[Any], index: int) -> Any:
        if not values:
            return None
        if index < 0:
            index += len(values)
        if index < 0 or index >= len(values):
            return None
        return values[index]

    @staticmethod
    def _to_xpath_root(data: Any) -> etree._Element | None:
        if isinstance(data, etree._Element):
            return data
        if isinstance(data, Tag):
            return etree.HTML(str(data))
        if isinstance(data, BeautifulSoup):
            return etree.HTML(str(data))
        if isinstance(data, str):
            return etree.HTML(data)
        return None

    @classmethod
    def _apply_post_ops(cls, value: Any, post_ops: list[tuple[str, str, str | None]]) -> Any:
        if not post_ops:
            return value
        return JsonPathExt._apply_post_ops(value, post_ops)

    @classmethod
    def _maybe_complete_url(cls, value: Any, rule: str, base_url: str) -> Any:
        if not base_url or value in (None, ""):
            return value

        if isinstance(value, list):
            return [cls._maybe_complete_url(item, rule, base_url) for item in value]

        if not isinstance(value, str):
            return value

        lowered_rule = rule.lower()
        should_complete = (
            "href" in lowered_rule
            or "url" in lowered_rule
            or value.startswith(("/", "./", "../"))
        )
        if not should_complete:
            return value

        return UrlUtils.resolve_relative(value, base_url)

    @classmethod
    def _looks_like_template(cls, rule: str) -> bool:
        return "{{" in rule or "{$" in rule or "}}" in rule

    @classmethod
    def _looks_like_xpath(cls, rule: str) -> bool:
        if rule.startswith("//") or rule.startswith("./"):
            return True
        if rule.startswith("/") and "{{" not in rule and "{$" not in rule:
            if any(marker in rule for marker in ("/text()", "/@", "[@", "//*[", "//")):
                return True
        return False

    @classmethod
    def _looks_like_html_selector(cls, rule: str, data: Any) -> bool:
        if isinstance(data, (Tag, BeautifulSoup, etree._Element)):
            return True
        if isinstance(data, str):
            if rule.startswith((".", "#", "class.", "id.", "tag.")):
                return True
            if any(
                marker in rule
                for marker in ("@text", "@html", "@href", "@src", "@textNodes")
            ):
                return True
        return rule.lower() in cls._VALUE_ACCESSORS

    @staticmethod
    def _strip_js_wrapper(rule: str) -> str:
        stripped = rule.strip()
        if stripped.lower().startswith("@js:"):
            return stripped[4:].strip()
        if stripped.lower().startswith("<js>") and stripped.lower().endswith("</js>"):
            return stripped[4:-5].strip()
        return stripped

    @staticmethod
    def _get_js_runtime(context: dict[str, Any]) -> JsRuntime:
        runtime = context.get("js_runtime")
        if isinstance(runtime, JsRuntime):
            return runtime
        if runtime is not None and callable(getattr(runtime, "execute", None)):
            return runtime
        return JsRuntime()


def select_values(raw_rule: str, sample: str | dict) -> list[str]:
    result = RuleSelector.extract(
        sample,
        raw_rule,
        "",
        isinstance(sample, str),
        as_list=True,
    )
    if not result.success or result.value is None:
        return []
    if isinstance(result.value, list):
        return [str(item) for item in result.value if item is not None]
    return [str(result.value)]
