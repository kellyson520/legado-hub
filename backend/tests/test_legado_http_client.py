def test_legado_http_client_does_not_advertise_brotli_without_decoder():
    from app.infrastructure.legado.engine.http_client import LegadoHttpClient

    assert "br" not in LegadoHttpClient.DEFAULT_HEADERS["Accept-Encoding"].lower()
