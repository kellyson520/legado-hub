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
