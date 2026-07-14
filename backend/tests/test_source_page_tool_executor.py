from dataclasses import dataclass

import pytest


@dataclass
class FakeResponse:
    url: str
    status_code: int = 200
    headers: dict[str, str] | None = None
    text: str = ""


class FakeHttp:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.closed = False

    async def get(self, url: str, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return FakeResponse(
            url=url,
            headers={"Content-Type": "text/html"},
            text=(
                '<form action="/search" method="post"><input name="q"></form>'
                '<a href="/book/1">A book</a>'
                '<main id="results"><p>Cookie=session-secret; Authorization: Bearer secret</p></main>'
            ),
        )

    async def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return FakeResponse(
            url=url,
            headers={"Content-Type": "text/html"},
            text='<a href="/book/2">Posted result</a>',
        )

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_page_tools_allow_target_origin_and_redact_sensitive_data():
    from app.application.services.source_page_tool_executor import SourcePageToolExecutor

    result = await SourcePageToolExecutor(
        'https://books.example/list', FakeHttp(),
    ).inspect({'url': '/search'})

    assert result.status == 'accepted'
    assert set(result.data) == {
        'url', 'status', 'response_kind', 'forms', 'links', 'dom_outline', 'excerpt',
    }
    assert result.data['url'] == 'https://books.example/search'
    assert result.data['status'] == 200
    assert result.data['response_kind'] == 'html'
    assert result.data['forms'][0]['method'] == 'POST'
    assert result.data['links'][0]['url'] == 'https://books.example/book/1'
    assert 'session-secret' not in result.data['excerpt']
    assert 'bearer secret' not in result.data['excerpt'].lower()
    assert '[redacted]' in result.data['excerpt']


@pytest.mark.asyncio
async def test_page_tools_reject_cross_origin_and_unsafe_requests():
    from app.application.services.source_page_tool_executor import SourcePageToolExecutor

    tools = SourcePageToolExecutor('https://books.example/list', FakeHttp())

    assert (
        await tools.request({'url': 'https://other.example/', 'method': 'GET'})
    ).error_code == 'cross_origin_url'
    assert (
        await tools.request({
            'url': '/search', 'method': 'POST', 'headers': {'Authorization': 'x'},
        })
    ).error_code == 'unsafe_headers'
    assert (
        await tools.request({'url': '/search', 'method': 'PUT'})
    ).error_code == 'unsupported_method'
    assert (
        await tools.request({'url': '/search', 'method': 'POST', 'form': {'q': 'x' * 4097}})
    ).error_code == 'request_body_too_large'


@pytest.mark.asyncio
async def test_page_request_posts_only_a_bounded_form_and_closes_client():
    from app.application.services.source_page_tool_executor import SourcePageToolExecutor

    client = FakeHttp()
    tools = SourcePageToolExecutor('https://books.example/list', client)

    result = await tools.request({
        'url': '/search', 'method': 'POST', 'form': {'q': 'novel'},
    })
    await tools.aclose()

    assert result.status == 'accepted'
    assert client.calls == [
        ('POST', 'https://books.example/search', {
            'data': {'q': 'novel'}, 'follow_redirects': False,
        }),
    ]
    assert client.closed is True


@pytest.mark.asyncio
async def test_page_evidence_redacts_all_cookie_and_authorization_values():
    from app.application.services.source_page_tool_executor import SourcePageToolExecutor

    class SensitiveHttp(FakeHttp):
        async def get(self, url: str, **kwargs):
            self.calls.append(("GET", url, kwargs))
            return FakeResponse(
                url=url,
                headers={"Content-Type": "text/html"},
                text=(
                    '<form method="Authorization: Basic method-secret">'
                    '<input name="Cookie: field-secret"></form>'
                    'Cookie: first-cookie-secret; second=second-cookie-secret; '
                    'Authorization: Basic authorization-secret '
                    'Cookie whitespace-cookie-secret; another=another-cookie-secret; '
                    'Authorization Bearer whitespace-authorization-secret'
                ),
            )

    result = await SourcePageToolExecutor(
        'https://books.example/list', SensitiveHttp(),
    ).inspect({'url': '/search'})

    serialized = repr(result.data)
    assert result.data['forms'][0]['method'] == 'OTHER'
    for secret in (
        'method-secret', 'field-secret', 'first-cookie-secret',
        'second-cookie-secret', 'authorization-secret', 'whitespace-cookie-secret',
        'another-cookie-secret', 'whitespace-authorization-secret',
    ):
        assert secret not in serialized


@pytest.mark.asyncio
async def test_page_summaries_preserve_html_structure_while_redacting_attributes():
    from app.application.services.source_page_tool_executor import SourcePageToolExecutor

    class AttributeHttp(FakeHttp):
        async def get(self, url: str, **kwargs):
            return FakeResponse(
                url=url,
                headers={"Content-Type": "text/html"},
                text=(
                    '<form action="/search" data-note="Authorization: Basic attribute-secret">'
                    '<input name="q" type="search"></form>'
                ),
            )

    result = await SourcePageToolExecutor(
        'https://books.example/list', AttributeHttp(),
    ).inspect({'url': '/search'})

    assert result.data['forms'] == [{
        'action': 'https://books.example/search',
        'method': 'GET',
        'fields': [{'name': 'q', 'type': 'search'}],
    }]
    assert 'attribute-secret' not in repr(result.data)


@pytest.mark.asyncio
async def test_page_evidence_redacts_whitespace_delimited_credentials():
    from app.application.services.source_page_tool_executor import SourcePageToolExecutor

    class WhitespaceHttp(FakeHttp):
        async def get(self, url: str, **kwargs):
            return FakeResponse(
                url=url,
                headers={"Content-Type": "text/plain"},
                text='Authorization Bearer whitespace-auth-secret Cookie whitespace-cookie-secret',
            )

    result = await SourcePageToolExecutor(
        'https://books.example/list', WhitespaceHttp(),
    ).inspect({'url': '/search'})

    assert 'whitespace-auth-secret' not in result.data['excerpt']
    assert 'whitespace-cookie-secret' not in result.data['excerpt']


@pytest.mark.asyncio
async def test_page_dom_outline_redacts_and_bounds_tag_names():
    from app.application.services.source_page_tool_executor import SourcePageToolExecutor

    class DomHttp(FakeHttp):
        async def get(self, url: str, **kwargs):
            return FakeResponse(
                url=url,
                headers={"Content-Type": "text/html"},
                text=f'<authorization=tag-secret-{"x" * 300}></authorization>',
            )

    result = await SourcePageToolExecutor(
        'https://books.example/list', DomHttp(),
    ).inspect({'url': '/search'})

    assert 'tag-secret' not in repr(result.data['dom_outline'])
    assert all(len(node['tag']) <= 240 for node in result.data['dom_outline'])


@pytest.mark.asyncio
async def test_page_tools_disable_redirect_following_for_injected_clients():
    from app.application.services.source_page_tool_executor import SourcePageToolExecutor

    class RedirectingHttp:
        def __init__(self):
            self.calls: list[tuple[str, str, dict]] = []
            self.foreign_origin_requests = 0

        async def get(self, url: str, **kwargs):
            return self._respond('GET', url, kwargs, 302)

        async def post(self, url: str, **kwargs):
            return self._respond('POST', url, kwargs, 307)

        def _respond(self, method: str, url: str, kwargs: dict, status_code: int):
            self.calls.append((method, url, kwargs))
            if kwargs.get('follow_redirects') is not False:
                self.foreign_origin_requests += 1
                return FakeResponse(url='https://other.example/redirected')
            return FakeResponse(
                url=url,
                status_code=status_code,
                headers={'Location': 'https://other.example/redirected'},
            )

    client = RedirectingHttp()
    tools = SourcePageToolExecutor('https://books.example/list', client)

    inspected = await tools.inspect({'url': '/search'})
    posted = await tools.request({'url': '/search', 'method': 'POST', 'form': {'q': 'novel'}})

    assert inspected.data['status'] == 302
    assert posted.data['status'] == 307
    assert client.foreign_origin_requests == 0
    assert all(call[2]['follow_redirects'] is False for call in client.calls)
