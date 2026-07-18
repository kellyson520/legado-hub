from __future__ import annotations

import json
from urllib.parse import urljoin, urlparse
from typing import Any


class SourceUrlPolicy:
    """Pure URL/header policy shared by source application services."""

    @staticmethod
    def resolve_relative(url: str, base_url: str) -> str:
        if not url:
            return ""
        if url.startswith(("http://", "https://", "data:", "ftp://")):
            return url
        try:
            if not base_url:
                return url
            if not base_url.endswith("/") and "." not in base_url.rsplit("/", 1)[-1]:
                base_url = base_url + "/"
            return urljoin(base_url, url)
        except Exception:
            return url

    @staticmethod
    def parse_headers(header_data: Any) -> dict[str, str]:
        if not header_data:
            return {}
        if isinstance(header_data, dict):
            return {str(key): str(value) for key, value in header_data.items()}
        if not isinstance(header_data, str) or not header_data.strip():
            return {}
        header_data = header_data.strip()
        try:
            parsed = json.loads(header_data)
            if isinstance(parsed, dict):
                return {str(key): str(value) for key, value in parsed.items()}
        except (json.JSONDecodeError, TypeError):
            pass
        headers: dict[str, str] = {}
        for line in header_data.split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip():
                headers[key.strip()] = value.strip()
        return headers

    @staticmethod
    def get_base_url(book_source_url: str) -> str:
        if not book_source_url:
            return ""
        url = book_source_url.split("#", 1)[0]
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return url
