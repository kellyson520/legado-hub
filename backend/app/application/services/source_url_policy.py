from __future__ import annotations

import json
from urllib.parse import urljoin, urlparse
from typing import Any

from app.core.url_safety import public_http_url_error


class SourceUrlPolicy:
    """Pure URL/header policy shared by source application services."""

    @classmethod
    def public_http_url_error(cls, value: Any) -> str | None:
        """Return a stable error for URLs that must never be fetched server-side.

        This policy intentionally rejects literal non-public address ranges and
        URL credentials. DNS resolution is enforced by the HTTP adapters at
        request time; keeping this function pure makes validation deterministic
        for tool schemas and unit tests.
        """
        return public_http_url_error(value)

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
