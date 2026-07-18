import pytest

from app.infrastructure.legado.engine.http_client import HttpResponse
from app.infrastructure.legado.engine.native_models import RuntimeResult
from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher


SOURCE = {
    "bookSourceName": "example",
    "bookSourceUrl": "https://example.test/",
    "searchUrl": "/search?q={{key}}",
    "ruleSearch": {
        "bookList": ".book",
        "name": "a@text",
        "bookUrl": "a@href",
    },
}


class FakeHttp:
    async def get(self, url, **kwargs):
        return HttpResponse(
            url=url,
            status=200,
            text="<div class='book'><a href='/book/1'>剑来</a></div>",
            headers={"content-type": "text/html"},
            is_html=True,
        )


class RecordingFacade:
    def __init__(self):
        self.stages = []

    def extract(self, content, rule, *, operation, stage, **kwargs):
        self.stages.append(stage)
        if operation == "extract_list":
            return RuntimeResult(success=True, value=[{"name": "剑来", "bookUrl": "/book/1"}], value_type="list")
        if isinstance(content, dict) and "name" in content:
            value = content["name"] if "text" in rule else content.get("bookUrl", "")
        else:
            value = "剑来" if "text" in rule else "/book/1"
        return RuntimeResult(success=True, value=value, value_type="string")


@pytest.mark.asyncio
async def test_fetcher_uses_facade_for_search_extraction():
    facade = RecordingFacade()
    fetcher = LegadoBookSourceFetcher(http_client=FakeHttp(), runtime_facade=facade)

    results = await fetcher.search(SOURCE, "剑来")

    assert results[0]["name"] == "剑来"
    assert results[0]["bookUrl"] == "https://example.test/book/1"
    assert facade.stages == ["search", "search", "search"]
