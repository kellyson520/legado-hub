async def test_fetcher_close_releases_http_and_js_runtime_once():
    from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher

    class FakeHttp:
        def __init__(self):
            self.close_calls = 0

        async def close(self):
            self.close_calls += 1

    class FakeRuntime:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    fetcher = LegadoBookSourceFetcher()
    http = FakeHttp()
    runtime = FakeRuntime()
    fetcher._http = http
    fetcher._js_runtime = runtime

    await fetcher.close()

    assert http.close_calls == 1
    assert runtime.close_calls == 1
