from __future__ import annotations

import json
import re
from typing import Any

try:
    from jsonpath_ng.ext import parse as parse_ext
except ImportError:  # pragma: no cover - dependency is expected in runtime
    parse_ext = None


class JsonPathExt:
    _cache: dict[str, Any] = {}
    HAS_EXT = parse_ext is not None

    @classmethod
    def query(cls, data: Any, path: str, default: Any = None) -> Any:
        if path is None:
            return default

        expression = str(path).strip()
        if not expression:
            return default

        if expression.startswith("{{") and expression.endswith("}}"):
            inner = expression[2:-2].strip()
            return cls.query(data, inner, default)

        last_value = default
        for alternative in cls._split_top_level(expression, "||"):
            base_path, post_ops = cls._split_post_ops(alternative)
            value = cls._execute_path(base_path.strip(), data)
            value = cls._apply_post_ops(value, post_ops)
            if not cls._is_empty(value):
                return value
            last_value = value

        return last_value

    @classmethod
    def query_list(cls, data: Any, path: str, default: Any = None) -> list[Any]:
        result = cls.query(data, path, default)
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return [result]

    @classmethod
    def query_first(cls, data: Any, path: str, default: Any = None) -> Any:
        result = cls.query(data, path, default)
        if isinstance(result, list):
            return result[0] if result else default
        return result

    @classmethod
    def fill_template(
        cls,
        template: str,
        data: Any,
        extra_vars: dict[str, Any] | None = None,
    ) -> str:
        if not template:
            return ""

        extra_vars = extra_vars or {}

        def replace_double(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            value = cls._resolve_template_expr(expr, data, extra_vars)
            return cls._stringify(value)

        rendered = re.sub(r"\{\{(.+?)\}\}", replace_double, template)

        def replace_single(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            value = cls._resolve_template_expr(expr, data, extra_vars)
            return cls._stringify(value)

        return re.sub(r"\{(\$[^{}]+)\}", replace_single, rendered)

    @classmethod
    def _resolve_template_expr(
        cls,
        expr: str,
        data: Any,
        extra_vars: dict[str, Any],
    ) -> Any:
        stripped = expr.strip()
        if not stripped:
            return ""

        if (
            (stripped.startswith('"') and stripped.endswith('"'))
            or (stripped.startswith("'") and stripped.endswith("'"))
        ):
            return stripped[1:-1]

        match = re.match(
            r"^(?P<base>.+?)\.match\(/(?P<pattern>.*?)/(?P<flags>[a-z]*)\)\[(?P<index>\d+)\]$",
            stripped,
        )
        if match:
            base_value = cls._resolve_template_expr(match.group("base"), data, extra_vars)
            if base_value is None:
                return ""
            flags = 0
            if "i" in match.group("flags"):
                flags |= re.IGNORECASE
            regex = re.search(match.group("pattern"), str(base_value), flags)
            if not regex:
                return ""
            group_index = int(match.group("index"))
            try:
                return regex.group(group_index)
            except IndexError:
                return ""

        cache_match = re.match(
            r"^cache\.(?P<method>getFromMemory|get)\((?P<quote>['\"])(?P<key>.+?)(?P=quote)\)$",
            stripped,
        )
        if cache_match:
            cache_store = extra_vars.get("cache")
            cache_key = cache_match.group("key")
            if isinstance(cache_store, dict):
                return cache_store.get(cache_key)
            if hasattr(cache_store, cache_match.group("method")):
                try:
                    return getattr(cache_store, cache_match.group("method"))(cache_key)
                except Exception:
                    return ""

        if stripped.startswith("$"):
            return cls.query(data, stripped)

        resolved = cls._resolve_reference(extra_vars, stripped)
        if resolved is not None:
            return resolved

        resolved = cls._resolve_reference({"result": data, **extra_vars}, stripped)
        if resolved is not None:
            return resolved

        if isinstance(data, (dict, list)):
            resolved = cls._resolve_reference(data, stripped)
            if resolved is not None:
                return resolved

        return stripped

    @classmethod
    def _execute_path(cls, path: str, data: Any) -> Any:
        if not path:
            return None

        if (
            (path.startswith('"') and path.endswith('"'))
            or (path.startswith("'") and path.endswith("'"))
        ):
            return path[1:-1]

        if path.startswith("$"):
            parser = cls._get_parser(path)
            if parser is not None and data is not None:
                try:
                    matches = parser.find(data)
                except Exception:
                    matches = []
                if matches:
                    values = [item.value for item in matches]
                    if len(values) == 1:
                        return values[0]
                    return values
            return cls._simple_jsonpath(data, path)

        return cls._resolve_reference(data, path)

    @classmethod
    def _get_parser(cls, expression: str) -> Any | None:
        if not cls.HAS_EXT:
            return None

        if expression in cls._cache:
            return cls._cache[expression]

        try:
            parser = parse_ext(expression)
        except Exception:
            parser = None

        if len(cls._cache) > 256:
            cls._cache.clear()
        cls._cache[expression] = parser
        return parser

    @classmethod
    def _simple_jsonpath(cls, data: Any, expression: str) -> Any:
        if data is None:
            return None

        expr = expression.strip()
        if expr.startswith("$.."):
            key = expr[3:]
            results: list[Any] = []
            cls._recursive_collect(data, key, results)
            if not results:
                return None
            if len(results) == 1:
                return results[0]
            return results

        if expr.startswith("$."):
            expr = expr[2:]
        elif expr == "$":
            return data

        tokens = cls._split_path(expr)
        current: Any = data

        for token in tokens:
            current = cls._walk_token(current, token)
            if current is None:
                return None

        return current

    @classmethod
    def _walk_token(cls, current: Any, token: str) -> Any:
        if token == "*":
            return current if isinstance(current, list) else None

        key, index = cls._parse_token(token)

        if key:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                mapped = []
                for item in current:
                    if isinstance(item, dict) and key in item:
                        mapped.append(item[key])
                current = mapped
            else:
                return None

        if index is None:
            return current

        if index == "*":
            if isinstance(current, list):
                return current
            return None

        try:
            idx = int(index)
        except (TypeError, ValueError):
            return None

        if not isinstance(current, list):
            return None

        if idx < 0:
            idx += len(current)
        if idx < 0 or idx >= len(current):
            return None
        return current[idx]

    @staticmethod
    def _parse_token(token: str) -> tuple[str, str | None]:
        token = token.strip()
        match = re.match(r"^(?P<key>[^\[\]]+)?\[(?P<index>\*|-?\d+)\]$", token)
        if not match:
            return token, None
        return (match.group("key") or "").strip(), match.group("index")

    @classmethod
    def _resolve_reference(cls, data: Any, expression: str) -> Any:
        if data is None:
            return None

        expr = expression.strip()
        if not expr:
            return None

        current = data
        for token in cls._split_path(expr):
            current = cls._walk_token(current, token)
            if current is None:
                return None
        return current

    @staticmethod
    def _recursive_collect(data: Any, key: str, results: list[Any]) -> None:
        if isinstance(data, dict):
            for item_key, item_value in data.items():
                if item_key == key:
                    results.append(item_value)
                JsonPathExt._recursive_collect(item_value, key, results)
        elif isinstance(data, list):
            for item in data:
                JsonPathExt._recursive_collect(item, key, results)

    @staticmethod
    def _split_path(path: str) -> list[str]:
        if not path:
            return []

        parts: list[str] = []
        current = []
        bracket_depth = 0
        for char in path:
            if char == "." and bracket_depth == 0:
                if current:
                    parts.append("".join(current))
                    current = []
                continue
            if char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth = max(0, bracket_depth - 1)
            current.append(char)

        if current:
            parts.append("".join(current))
        return parts

    @staticmethod
    def _split_top_level(text: str, token: str) -> list[str]:
        if not text or token not in text:
            return [text]

        parts: list[str] = []
        current: list[str] = []
        brace_depth = 0
        bracket_depth = 0
        paren_depth = 0
        quote: str | None = None
        i = 0

        while i < len(text):
            char = text[i]
            next_char = text[i + 1] if i + 1 < len(text) else ""

            if quote:
                current.append(char)
                if char == quote and text[i - 1] != "\\":
                    quote = None
                i += 1
                continue

            if char in {"'", '"'}:
                quote = char
                current.append(char)
                i += 1
                continue

            if char == "{" and next_char == "{":
                brace_depth += 1
                current.extend([char, next_char])
                i += 2
                continue
            if char == "}" and next_char == "}" and brace_depth > 0:
                brace_depth -= 1
                current.extend([char, next_char])
                i += 2
                continue

            if char == "{":
                brace_depth += 1
            elif char == "}" and brace_depth > 0:
                brace_depth -= 1
            elif char == "[":
                bracket_depth += 1
            elif char == "]" and bracket_depth > 0:
                bracket_depth -= 1
            elif char == "(":
                paren_depth += 1
            elif char == ")" and paren_depth > 0:
                paren_depth -= 1

            if (
                brace_depth == 0
                and bracket_depth == 0
                and paren_depth == 0
                and text.startswith(token, i)
            ):
                parts.append("".join(current))
                current = []
                i += len(token)
                continue

            current.append(char)
            i += 1

        parts.append("".join(current))
        return parts

    @classmethod
    def _split_post_ops(cls, expression: str) -> tuple[str, list[tuple[str, str, str | None]]]:
        marker_index = cls._find_top_level_marker(expression, "##")
        if marker_index < 0:
            return expression, []

        base = expression[:marker_index]
        rest = expression[marker_index + 2 :]
        if "##" in rest:
            pattern, replacement = rest.split("##", 1)
            return base, [("regex", pattern, replacement)]
        return base, [("regex", rest, None)]

    @classmethod
    def _find_top_level_marker(cls, text: str, marker: str) -> int:
        quote: str | None = None
        brace_depth = 0
        bracket_depth = 0
        paren_depth = 0

        i = 0
        while i < len(text):
            char = text[i]
            next_char = text[i + 1] if i + 1 < len(text) else ""

            if quote:
                if char == quote and text[i - 1] != "\\":
                    quote = None
                i += 1
                continue

            if char in {"'", '"'}:
                quote = char
                i += 1
                continue

            if char == "{" and next_char == "{":
                brace_depth += 1
                i += 2
                continue
            if char == "}" and next_char == "}" and brace_depth > 0:
                brace_depth -= 1
                i += 2
                continue

            if char == "{":
                brace_depth += 1
            elif char == "}" and brace_depth > 0:
                brace_depth -= 1
            elif char == "[":
                bracket_depth += 1
            elif char == "]" and bracket_depth > 0:
                bracket_depth -= 1
            elif char == "(":
                paren_depth += 1
            elif char == ")" and paren_depth > 0:
                paren_depth -= 1

            if (
                brace_depth == 0
                and bracket_depth == 0
                and paren_depth == 0
                and text.startswith(marker, i)
            ):
                return i
            i += 1

        return -1

    @staticmethod
    def _apply_post_ops(value: Any, post_ops: list[tuple[str, str, str | None]]) -> Any:
        result = value
        for op_kind, pattern, replacement in post_ops:
            if op_kind != "regex":
                continue

            if isinstance(result, list):
                result = [
                    JsonPathExt._apply_regex(item, pattern, replacement)
                    for item in result
                ]
            else:
                result = JsonPathExt._apply_regex(result, pattern, replacement)
        return result

    @staticmethod
    def _apply_regex(value: Any, pattern: str, replacement: str | None) -> Any:
        if value is None:
            return None

        text = str(value)
        try:
            if replacement is None:
                return re.sub(pattern, "", text)
            return re.sub(pattern, replacement, text)
        except re.error:
            return value

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) == 0
        return False

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)


def run_jsonpath(expression: str, sample: dict | list | None) -> list[str]:
    result = JsonPathExt.query(sample, expression)
    if result is None:
        return []
    if isinstance(result, list):
        return [JsonPathExt._stringify(item) for item in result if item is not None]
    return [JsonPathExt._stringify(result)]
