import pytest


class FakePage:
    def __init__(self):
        self.calls = []

    async def evaluate(self, _script, payload):
        self.calls.append(payload)
        return {
            'url': payload['url'],
            'status': 200,
            'headers': {'content-type': 'text/html; charset=utf-8'},
            'text': '<article>' + ('x' * 100) + '</article>',
        }


@pytest.mark.asyncio
async def test_browser_http_client_returns_legado_response_only_for_active_same_origin_page():
    from app.infrastructure.browser.browser_http_client import BrowserHttpClient

    page = FakePage()
    client = BrowserHttpClient(page=page, allowed_origins={'https://books.example.test'})

    response = await client.get('https://books.example.test/chapter/1')
    blocked = await client.get('https://other.example.test/chapter/1')

    assert response.success is True
    assert response.is_html is True
    assert response.text.startswith('<article>')
    assert blocked.error == 'cross_origin'
    assert page.calls == [{'url': 'https://books.example.test/chapter/1', 'method': 'GET', 'body': None, 'headers': {}}]


def test_legado_fetcher_uses_the_supplied_browser_transport():
    from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher

    transport = object()

    assert LegadoBookSourceFetcher(http_client=transport)._http is transport
