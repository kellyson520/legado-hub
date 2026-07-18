import asyncio
import time

import pytest

from app.infrastructure.legado.engine.http_client import HttpResponse
from app.infrastructure.legado.engine.runtime_bridge import RuntimeBridge


class FakeHttp:
    def __init__(self, delay=0.0):
        self.delay = delay
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if self.delay:
            await asyncio.sleep(self.delay)
        return HttpResponse(url=url, status=200, text='{"ok":true}', headers={"content-type": "application/json"}, is_json=True)

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return HttpResponse(url=url, status=201, text="created", headers={}, is_html=False)


def test_bridge_request_uses_existing_http_client():
    http = FakeHttp()
    bridge = RuntimeBridge(http_client=http, timeout=1.0)

    response = bridge.handle({"method": "GET", "url": "https://example.test"})

    assert response["status"] == 200
    assert response["text"] == '{"ok":true}'
    assert http.calls[0][0:2] == ("GET", "https://example.test")


def test_bridge_timeout_returns_stable_error():
    bridge = RuntimeBridge(http_client=FakeHttp(delay=0.1), timeout=0.01)

    response = bridge.handle({"method": "GET", "url": "https://example.test"})

    assert response["error_code"] == "BRIDGE_TIMEOUT"


def test_bridge_rejects_empty_url():
    response = RuntimeBridge(http_client=FakeHttp()).handle({"method": "GET", "url": ""})
    assert response["error_code"] == "EMPTY_URL"


def test_cache_bridge_is_scoped_and_supports_delete():
    bridge = RuntimeBridge(http_client=FakeHttp(), cache={})

    assert bridge.handle_cache({"op": "get", "scope": "source-a", "key": "token"})["found"] is False
    bridge.handle_cache({"op": "put", "scope": "source-a", "key": "token", "value": "abc"})
    assert bridge.handle_cache({"op": "get", "scope": "source-a", "key": "token"})["value"] == "abc"
    assert bridge.handle_cache({"op": "get", "scope": "source-b", "key": "token"})["found"] is False
    bridge.handle_cache({"op": "delete", "scope": "source-a", "key": "token"})
    assert bridge.handle_cache({"op": "get", "scope": "source-a", "key": "token"})["found"] is False
