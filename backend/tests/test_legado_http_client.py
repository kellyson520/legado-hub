import pytest


def test_legado_http_client_does_not_advertise_brotli_without_decoder():
    from app.infrastructure.legado.engine.http_client import LegadoHttpClient

    assert "br" not in LegadoHttpClient.DEFAULT_HEADERS["Accept-Encoding"].lower()


@pytest.mark.asyncio
async def test_public_address_resolver_rejects_private_dns_answers(monkeypatch):
    import aiohttp.resolver

    from app.infrastructure.legado.engine.http_client import PublicAddressResolver

    async def fake_resolve(_self, _host, _port=0, _family=0):
        return [{"host": "127.0.0.1", "port": 80, "family": 2, "proto": 6, "flags": 0}]

    monkeypatch.setattr(aiohttp.resolver.DefaultResolver, "resolve", fake_resolve)
    resolver = PublicAddressResolver()

    with pytest.raises(OSError, match="unsafe resolved address"):
        await resolver.resolve("example.com", 80)

    await resolver.close()


@pytest.mark.asyncio
async def test_legado_http_client_rejects_private_dns_ip_override():
    from app.infrastructure.legado.engine.http_client import LegadoHttpClient

    client = LegadoHttpClient(max_retries=0)
    response = await client.get("https://example.com/books", dns_ip="127.0.0.1")

    assert response.status == 0
    assert response.error == "unsafe_dns_ip"


@pytest.mark.asyncio
async def test_legado_http_client_rejects_malformed_dns_ip_override():
    from app.infrastructure.legado.engine.http_client import LegadoHttpClient

    async with LegadoHttpClient() as client:
        response = await client.get("https://example.com/books", dns_ip="not-an-ip")

    assert response.error == "invalid_dns_ip"


@pytest.mark.asyncio
async def test_legado_http_client_rechecks_each_redirect_before_following():
    from app.infrastructure.legado.engine.http_client import LegadoHttpClient

    class FakeResponse:
        status = 302
        headers = {"Location": "http://127.0.0.1/private"}
        url = "https://public.example/books"
        charset = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def read(self):
            return b""

    class FakeSession:
        def __init__(self):
            self.calls = []
            self.closed = False

        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            return FakeResponse()

        async def close(self):
            self.closed = True

    client = LegadoHttpClient(max_retries=0)
    session = FakeSession()
    client._session = session
    response = await client.get("https://public.example/books")

    assert response.error == "unsafe_redirect:unsafe"
    assert len(session.calls) == 1
    assert session.calls[0][2]["allow_redirects"] is False
    await client.close()


@pytest.mark.asyncio
async def test_legado_http_client_honors_redirect_disable_flag():
    from app.infrastructure.legado.engine.http_client import LegadoHttpClient

    class FakeResponse:
        status = 302
        headers = {"Location": "http://127.0.0.1/private", "Content-Type": "text/plain"}
        url = "https://public.example/books"
        charset = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def read(self):
            return b"redirect"

    class FakeSession:
        closed = False

        def request(self, _method, _url, **kwargs):
            assert kwargs["allow_redirects"] is False
            return FakeResponse()

        async def close(self):
            return None

    client = LegadoHttpClient(max_retries=0)
    client._session = FakeSession()
    response = await client.get("https://public.example/books", allow_redirects=False)

    assert response.status == 302
    assert response.error is None
    await client.close()


@pytest.mark.asyncio
async def test_legado_http_client_drops_sensitive_headers_on_cross_origin_redirect():
    from app.infrastructure.legado.engine.http_client import LegadoHttpClient

    class FakeResponse:
        def __init__(self, status, headers, body=b""):
            self.status = status
            self.headers = headers
            self.url = "https://public.example/books"
            self.charset = None
            self._body = body

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def read(self):
            return self._body

    class FakeSession:
        closed = False

        def __init__(self):
            self.calls = []

        def request(self, _method, url, **kwargs):
            self.calls.append((url, kwargs))
            if len(self.calls) == 1:
                return FakeResponse(302, {"Location": "https://other.example/next"})
            return FakeResponse(200, {"Content-Type": "text/plain"}, b"ok")

        async def close(self):
            return None

    client = LegadoHttpClient(max_retries=0)
    session = FakeSession()
    client._session = session
    response = await client.get(
        "https://public.example/books",
        headers={"Authorization": "Bearer secret", "Cookie": "session=secret", "X-Trace": "keep"},
    )

    assert response.status == 200
    assert session.calls[1][1]["headers"] == {"X-Trace": "keep"}
    await client.close()
