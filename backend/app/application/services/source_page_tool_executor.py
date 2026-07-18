from __future__ import annotations

import inspect
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.application.ports.http import AsyncHttpClient
from app.domain.entities.agent_runtime import ToolResult
from app.core.url_safety import public_http_url_error


_MAX_REQUEST_BODY_BYTES = 4 * 1024
_MAX_EXCERPT_CHARS = 4 * 1024
_MAX_DOCUMENT_CHARS = 64 * 1024
_MAX_FORMS = 12
_MAX_FORM_FIELDS = 16
_MAX_LINKS = 24
_MAX_DOM_NODES = 40
_MAX_TEXT_CHARS = 240
_MAX_URL_CHARS = 2 * 1024
_AUTHORIZATION_VALUE = re.compile(r'(?i)\bauthorization\b\s*(?:[:=]\s*|\s+)[^;<>\r\n]+')
_COOKIE_VALUE = re.compile(r'(?i)\bcookie\b\s*(?:[:=]\s*|\s+)[^<>\r\n]+')


class SourcePageToolExecutor:
    """Bounded public-page inspection scoped to one submitted source origin."""

    def __init__(self, target_url: str, client: AsyncHttpClient | None = None):
        target = self._normalise_http_url(target_url)
        if target is None or public_http_url_error(target) is not None:
            raise ValueError('target_url must be an absolute http(s) URL')
        self._target_url = target
        self._target_origin = self._origin(target)
        self._client = client or _UnconfiguredHttpClient()

    def handlers(self) -> dict[str, Any]:
        return {
            'page.inspect': self.inspect,
            'page.request': self.request,
        }

    async def inspect(self, arguments: dict[str, Any]) -> ToolResult:
        """GET a same-origin page and return bounded, sanitised page evidence."""
        if not isinstance(arguments, Mapping):
            return self._reject('invalid_page_arguments')
        if 'headers' in arguments:
            return self._reject('unsafe_headers')
        if 'method' in arguments and str(arguments['method']).upper() != 'GET':
            return self._reject('unsupported_method')

        url, error_code = self._resolve_same_origin(arguments.get('url', self._target_url))
        if error_code:
            return self._reject(error_code)
        return await self._fetch('GET', url)

    async def request(self, arguments: dict[str, Any]) -> ToolResult:
        """Perform only same-origin GET or form-encoded POST requests."""
        if not isinstance(arguments, Mapping):
            return self._reject('invalid_page_arguments')
        if 'headers' in arguments:
            return self._reject('unsafe_headers')
        if any(key in arguments for key in ('body', 'data', 'json', 'content')):
            return self._reject('invalid_form_request')

        method = arguments.get('method', 'GET')
        if not isinstance(method, str) or method.upper() not in {'GET', 'POST'}:
            return self._reject('unsupported_method')
        method = method.upper()

        url, error_code = self._resolve_same_origin(arguments.get('url', self._target_url))
        if error_code:
            return self._reject(error_code)

        form = arguments.get('form')
        if method == 'GET':
            if form is not None:
                return self._reject('invalid_form_request')
            return await self._fetch('GET', url)

        if form is None:
            form = {}
        normalised_form = self._normalise_form(form)
        if normalised_form is None:
            return self._reject('invalid_form_request')
        if len(urlencode(normalised_form).encode('utf-8')) > _MAX_REQUEST_BODY_BYTES:
            return self._reject('request_body_too_large')
        return await self._fetch('POST', url, form=normalised_form)

    async def aclose(self) -> None:
        close = getattr(self._client, 'aclose', None)
        if not callable(close):
            close = getattr(self._client, 'close', None)
        if not callable(close):
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    async def _fetch(self, method: str, url: str, *, form: dict[str, str] | None = None) -> ToolResult:
        try:
            request = getattr(self._client, method.lower(), None)
            if not callable(request):
                return self._reject('page_request_unavailable')
            kwargs = {'follow_redirects': False}
            if method == 'POST':
                kwargs['data'] = form
            result = request(url, **kwargs)
            response = await result if inspect.isawaitable(result) else result
        except Exception:
            return self._reject('page_request_failed')

        response_url = str(getattr(response, 'url', '') or url)
        if self._origin(response_url) != self._target_origin:
            return self._reject('cross_origin_redirect')
        return ToolResult(status='accepted', data=self._summarise_response(response, response_url))

    def _resolve_same_origin(self, raw_url: Any) -> tuple[str, str | None]:
        if not isinstance(raw_url, str) or not raw_url.strip():
            return '', 'invalid_page_url'
        resolved = self._normalise_http_url(urljoin(self._target_url, raw_url.strip()))
        if resolved is None:
            return '', 'invalid_page_url'
        if self._origin(resolved) != self._target_origin:
            return '', 'cross_origin_url'
        return resolved, None

    @staticmethod
    def _normalise_http_url(value: str) -> str | None:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {'http', 'https'} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', parsed.query, ''))

    @staticmethod
    def _origin(value: str) -> tuple[str, str, int | None] | None:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {'http', 'https'} or not parsed.hostname:
            return None
        try:
            port = parsed.port
        except ValueError:
            return None
        if port is None:
            port = 443 if parsed.scheme.lower() == 'https' else 80
        return parsed.scheme.lower(), parsed.hostname.lower(), port

    @staticmethod
    def _normalise_form(value: Any) -> dict[str, str] | None:
        if not isinstance(value, Mapping):
            return None
        form: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or isinstance(item, (Mapping, list, tuple, set)):
                return None
            if item is None:
                return None
            form[key] = str(item)
        return form

    def _summarise_response(self, response: Any, response_url: str) -> dict[str, Any]:
        headers = getattr(response, 'headers', {}) or {}
        content_type = str(next(
            (value for key, value in headers.items() if str(key).lower() == 'content-type'),
            '',
        )).lower()
        response_kind = self._response_kind(content_type)
        document = str(getattr(response, 'text', '') or '')[:_MAX_DOCUMENT_CHARS]
        forms: list[dict[str, Any]] = []
        links: list[dict[str, str]] = []
        dom_outline: list[dict[str, Any]] = []
        excerpt = self._bounded_text(document, _MAX_EXCERPT_CHARS)

        if response_kind == 'html':
            soup = BeautifulSoup(document, 'lxml')
            forms = self._forms(soup, response_url)
            links = self._links(soup, response_url)
            dom_outline = self._dom_outline(soup)
            for element in soup(['script', 'style', 'noscript']):
                element.decompose()
            excerpt = self._bounded_text(soup.get_text(' ', strip=True), _MAX_EXCERPT_CHARS)

        return {
            'url': self._safe_url(response_url),
            'status': int(getattr(response, 'status_code', getattr(response, 'status', 0)) or 0),
            'response_kind': response_kind,
            'forms': forms,
            'links': links,
            'dom_outline': dom_outline,
            'excerpt': excerpt,
        }

    @staticmethod
    def _response_kind(content_type: str) -> str:
        if 'html' in content_type or 'xhtml' in content_type:
            return 'html'
        if 'json' in content_type or content_type.endswith('+json'):
            return 'json'
        if content_type.startswith('text/') or not content_type:
            return 'text'
        return 'binary'

    def _forms(self, soup: BeautifulSoup, base_url: str) -> list[dict[str, Any]]:
        forms = []
        for form in soup.find_all('form', limit=_MAX_FORMS):
            action = urljoin(base_url, str(form.get('action') or base_url))
            fields = []
            for field in form.find_all(['input', 'select', 'textarea', 'button'], limit=_MAX_FORM_FIELDS):
                name = field.get('name')
                if not name:
                    continue
                fields.append({
                    'name': self._bounded_text(str(name), _MAX_TEXT_CHARS),
                    'type': self._bounded_text(str(field.get('type') or field.name), _MAX_TEXT_CHARS),
                })
            forms.append({
                'action': self._safe_url(action),
                'method': self._form_method(form.get('method')),
                'fields': fields,
            })
        return forms

    def _links(self, soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
        links = []
        for link in soup.find_all('a', href=True, limit=_MAX_LINKS):
            resolved = urljoin(base_url, str(link.get('href') or ''))
            links.append({
                'url': self._safe_url(resolved),
                'text': self._bounded_text(link.get_text(' ', strip=True), _MAX_TEXT_CHARS),
            })
        return links

    def _dom_outline(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        nodes = []
        for element in soup.find_all(limit=_MAX_DOM_NODES):
            classes = [self._bounded_text(str(item), _MAX_TEXT_CHARS) for item in (element.get('class') or [])[:4]]
            nodes.append({
                'tag': self._bounded_text(str(element.name), _MAX_TEXT_CHARS),
                'id': self._bounded_text(str(element.get('id') or ''), _MAX_TEXT_CHARS),
                'classes': classes,
            })
        return nodes

    @staticmethod
    def _redact(value: str) -> str:
        redacted = _AUTHORIZATION_VALUE.sub('authorization=[redacted]', value)
        return _COOKIE_VALUE.sub('cookie=[redacted]', redacted)

    def _form_method(self, value: Any) -> str:
        method = self._bounded_text(str(value or 'GET'), _MAX_TEXT_CHARS).upper()
        return method if method in {'GET', 'POST'} else 'OTHER'

    def _safe_url(self, value: str) -> str:
        parsed = urlsplit(value)
        netloc = parsed.hostname or ''
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port is not None:
            netloc = f'{netloc}:{port}'
        return self._bounded_text(
            urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, '')),
            _MAX_URL_CHARS,
        )

    def _bounded_text(self, value: str, limit: int) -> str:
        compact = ' '.join(self._redact(str(value)).split())
        return compact[:limit]

    @staticmethod
    def _reject(error_code: str) -> ToolResult:
        return ToolResult(status='rejected', error_code=error_code)


class _UnconfiguredHttpClient:
    async def get(self, _url: str, **_kwargs):
        raise RuntimeError('source page HTTP client is not configured')

    async def post(self, _url: str, **_kwargs):
        raise RuntimeError('source page HTTP client is not configured')

    async def aclose(self) -> None:
        return None
