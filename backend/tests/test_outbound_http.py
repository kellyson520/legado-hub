import pytest


def _private_resolver(*_args, **_kwargs):
    return [(0, 0, 0, "", ("127.0.0.1", 80))]


def _public_resolver(*_args, **_kwargs):
    return [(0, 0, 0, "", ("93.184.216.34", 80))]


def _redirect_resolver(hostname, *_args, **_kwargs):
    if hostname == "private.example":
        return [(0, 0, 0, "", ("127.0.0.1", 80))]
    return [(0, 0, 0, "", ("93.184.216.34", 80))]


def _multi_host_public_resolver(*_args, **_kwargs):
    return [(0, 0, 0, "", ("93.184.216.34", 80))]


def test_safe_sync_http_client_rejects_domains_resolving_to_private_addresses():
    from app.infrastructure.http.outbound import SafeSyncHttpClient

    client = SafeSyncHttpClient(resolver=_private_resolver)
    with pytest.raises(ValueError, match="unsafe outbound URL"):
        client.get("https://controlled.example/books")


def test_safe_sync_http_client_pins_resolved_public_ip_and_preserves_host(monkeypatch):
    from app.infrastructure.http import outbound
    calls = []

    def fake_handle_request(_transport, request):
        calls.append(request)
        return outbound.httpx.Response(200, request=request, text="ok")

    monkeypatch.setattr(outbound.httpx.HTTPTransport, "handle_request", fake_handle_request)
    transport = outbound._PinnedSyncTransport(resolver=_public_resolver)
    response = transport.handle_request(outbound.httpx.Request("GET", "https://controlled.example/books"))

    assert response.status_code == 200
    assert len(calls) == 1
    assert str(calls[0].url) == "https://93.184.216.34/books"
    assert calls[0].headers["host"] == "controlled.example"
    assert calls[0].extensions["sni_hostname"] == "controlled.example"


def test_safe_sync_http_client_rechecks_each_redirect(monkeypatch):
    from app.infrastructure.http import outbound
    from app.infrastructure.http.outbound import SafeSyncHttpClient

    calls = []

    class FakeResponse:
        status_code = 302
        headers = {"location": "https://private.example/secret"}

        def close(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse()

        def close(self):
            return None

    monkeypatch.setattr(outbound.httpx, "Client", FakeClient)

    with SafeSyncHttpClient(resolver=_redirect_resolver, follow_redirects=True) as client:
        with pytest.raises(ValueError, match="unsafe outbound URL"):
            client.get("https://public.example/start")

    assert calls == [("GET", "https://public.example/start", {})]


def test_safe_sync_http_client_drops_sensitive_headers_on_cross_origin_redirect(monkeypatch):
    from app.infrastructure.http import outbound
    from app.infrastructure.http.outbound import SafeSyncHttpClient

    calls = []

    class FakeResponse:
        def __init__(self, status_code, headers):
            self.status_code = status_code
            self.headers = headers

        def close(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            if len(calls) == 1:
                return FakeResponse(302, {"location": "https://other.example/next"})
            return FakeResponse(200, {})

        def close(self):
            return None

    monkeypatch.setattr(outbound.httpx, "Client", FakeClient)

    with SafeSyncHttpClient(resolver=_multi_host_public_resolver, follow_redirects=True) as client:
        response = client.get(
            "https://public.example/start",
            headers={
                "Authorization": "Bearer secret",
                "Cookie": "session=secret",
                "X-Trace": "keep",
            },
        )

    assert response.status_code == 200
    assert calls[0][2]["headers"]["Authorization"] == "Bearer secret"
    assert calls[1][2]["headers"] == {"X-Trace": "keep"}


def test_redirect_drops_auth_and_cookies_without_headers():
    from app.infrastructure.http.outbound import _redirect_request

    method, kwargs = _redirect_request(
        "GET",
        {"auth": ("user", "secret"), "cookies": {"session": "secret"}},
        302,
        current_url="https://public.example/start",
        next_url="https://other.example/next",
    )

    assert method == "GET"
    assert kwargs == {}


@pytest.mark.asyncio
async def test_safe_async_transport_pins_ip_and_keeps_https_sni(monkeypatch):
    from app.infrastructure.http import outbound

    calls = []

    async def fake_handle_request(_transport, request):
        calls.append(request)
        return outbound.httpx.Response(200, request=request, text="ok")

    monkeypatch.setattr(outbound.httpx.AsyncHTTPTransport, "handle_async_request", fake_handle_request)
    transport = outbound._PinnedAsyncTransport(resolver=_public_resolver)
    response = await transport.handle_async_request(
        outbound.httpx.Request("GET", "https://controlled.example/books")
    )

    assert response.status_code == 200
    assert str(calls[0].url) == "https://93.184.216.34/books"
    assert calls[0].headers["host"] == "controlled.example"
    assert calls[0].extensions["sni_hostname"] == "controlled.example"


@pytest.mark.asyncio
async def test_safe_async_http_client_drops_sensitive_headers_on_cross_origin_redirect(monkeypatch):
    from app.infrastructure.http import outbound
    from app.infrastructure.http.outbound import SafeAsyncHttpClient

    calls = []

    class FakeResponse:
        def __init__(self, status_code, headers):
            self.status_code = status_code
            self.headers = headers

        async def aclose(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            if len(calls) == 1:
                return FakeResponse(302, {"location": "https://other.example/next"})
            return FakeResponse(200, {})

        async def aclose(self):
            return None

    monkeypatch.setattr(outbound.httpx, "AsyncClient", FakeClient)
    client = SafeAsyncHttpClient(resolver=_multi_host_public_resolver, follow_redirects=True)
    try:
        response = await client.get(
            "https://public.example/start",
            headers={"Authorization": "Bearer secret", "Cookie": "session=secret", "X-Trace": "keep"},
        )
    finally:
        await client.aclose()

    assert response.status_code == 200
    assert calls[1][2]["headers"] == {"X-Trace": "keep"}


@pytest.mark.asyncio
async def test_safe_async_http_client_rejects_domains_resolving_to_private_addresses():
    from app.infrastructure.http.outbound import SafeAsyncHttpClient

    client = SafeAsyncHttpClient(resolver=_private_resolver)
    try:
        with pytest.raises(ValueError, match="unsafe outbound URL"):
            await client.get("https://controlled.example/books")
    finally:
        await client.aclose()


def test_safe_webhook_sender_allows_public_resolution_and_preserves_payload(monkeypatch):
    from app.infrastructure.http import outbound
    from app.infrastructure.http.outbound import SafeWebhookSender
    from app.domain.entities.event_delivery import EventDelivery

    class FakeResponse:
        status_code = 202
        text = "accepted"

    class FakeClient:
        def __init__(self, **_kwargs):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return FakeResponse()

        def request(self, method, url, **kwargs):
            assert method == "POST"
            return self.post(url, **kwargs)

        def close(self):
            return None

    fake = FakeClient()
    client_kwargs = {}

    def build_fake_client(**kwargs):
        client_kwargs.update(kwargs)
        return fake

    monkeypatch.setattr(outbound.httpx, "Client", build_fake_client)
    delivery = EventDelivery(
        event_id="event-1",
        event_type="chapter.ready",
        tenant_id="tenant-1",
        target_url="https://callback.example/webhook",
        body='{"ok":true}',
        headers={"Content-Type": "application/json"},
    )

    result = SafeWebhookSender(resolver=_public_resolver)(delivery)

    assert result.status_code == 202
    assert fake.calls == [(
        "https://callback.example/webhook",
        {"content": b'{"ok":true}', "headers": {"Content-Type": "application/json"}},
    )]
    assert getattr(getattr(client_kwargs["transport"], "_pool", None), "_ssl_context", None) is not None
