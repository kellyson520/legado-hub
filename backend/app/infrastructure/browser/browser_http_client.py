from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.infrastructure.legado.engine.http_client import HttpResponse


_BROWSER_FETCH = """
async ({url, method, body, headers}) => {
  const response = await fetch(url, {
    method,
    body,
    headers,
    credentials: 'include',
    redirect: 'follow',
  });
  const responseHeaders = {};
  for (const [key, value] of response.headers.entries()) responseHeaders[key] = value;
  return {
    url: response.url,
    status: response.status,
    headers: responseHeaders,
    text: await response.text(),
  };
}
"""


class BrowserHttpClient:
    """Bounded Legado transport that keeps requests inside one browser context."""

    def __init__(self, *, page, allowed_origins: set[str]):
        self._page = page
        self._allowed_origins = set(allowed_origins)

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **_kwargs,
    ) -> HttpResponse:
        if params:
            url = self._with_query(url, params)
        return await self._request('GET', url, body=None, headers=headers or {})

    async def post(
        self,
        url: str,
        data: Any = None,
        json_data: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **_kwargs,
    ) -> HttpResponse:
        if params:
            url = self._with_query(url, params)
        request_headers = dict(headers or {})
        if json_data is not None:
            request_headers.setdefault('Content-Type', 'application/json')
            body = json.dumps(json_data, ensure_ascii=False)
        elif isinstance(data, dict):
            request_headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
            body = urlencode(data)
        elif data is None:
            body = None
        else:
            body = str(data)
        return await self._request('POST', url, body=body, headers=request_headers)

    async def close(self) -> None:
        return None

    async def _request(self, method: str, url: str, *, body: str | None, headers: dict[str, str]) -> HttpResponse:
        if self._origin(url) not in self._allowed_origins:
            return HttpResponse(url=url, status=0, error='cross_origin')
        try:
            result = await self._page.evaluate(
                _BROWSER_FETCH,
                {'url': url, 'method': method, 'body': body, 'headers': headers},
            )
        except Exception:
            return HttpResponse(url=url, status=0, error='browser_request_failed')
        if not isinstance(result, dict):
            return HttpResponse(url=url, status=0, error='browser_request_failed')
        response_url = str(result.get('url') or url)
        if self._origin(response_url) not in self._allowed_origins:
            return HttpResponse(url=response_url, status=0, error='cross_origin_redirect')
        response_headers = result.get('headers')
        headers_dict = {
            str(key): str(value)
            for key, value in response_headers.items()
        } if isinstance(response_headers, dict) else {}
        text = str(result.get('text') or '')
        content_type = headers_dict.get('content-type') or headers_dict.get('Content-Type') or ''
        is_json = 'json' in content_type.lower()
        parsed_json = None
        if is_json:
            try:
                parsed_json = json.loads(text)
            except (TypeError, ValueError):
                is_json = False
        return HttpResponse(
            url=response_url,
            status=int(result.get('status') or 0),
            headers=headers_dict,
            text=text,
            content=text.encode('utf-8'),
            json_data=parsed_json,
            is_json=is_json,
            is_html='text/html' in content_type.lower() or text.lstrip().startswith('<'),
        )

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlsplit(url)
        return f'{parsed.scheme}://{parsed.netloc}' if parsed.scheme and parsed.netloc else ''

    @staticmethod
    def _with_query(url: str, params: dict[str, Any]) -> str:
        parsed = urlsplit(url)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query.extend((str(key), str(value)) for key, value in params.items())
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
