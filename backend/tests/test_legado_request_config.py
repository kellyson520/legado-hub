import pytest

from app.infrastructure.legado.engine.http_client import HttpResponse
from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher


@pytest.mark.asyncio
async def test_fetcher_get_toc_honors_post_request_config_in_book_url():
    class FakeHttp:
        async def post(self, url, data=None, json_data=None, headers=None):
            assert url == "https://api.example.com/detail"
            assert data == "blogdomain=demo&postid=1"
            return HttpResponse(
                url=url,
                status=200,
                is_json=True,
                json_data={"data": {"chapters": [{"title": "第一章", "url": "/chapter/1"}]}},
            )

    fetcher = LegadoBookSourceFetcher()
    fetcher._http = FakeHttp()
    source = {
        "bookSourceUrl": "https://api.example.com",
        "ruleToc": {
            "chapterList": "$.data.chapters[*]",
            "chapterName": "$.title",
            "chapterUrl": "$.url",
        },
    }

    chapters = await fetcher.get_toc(
        source,
        'https://api.example.com/detail,{"method":"POST","body":"blogdomain=demo&postid=1"}',
    )

    assert chapters == [
        {
            "title": "第一章",
            "url": "https://api.example.com/chapter/1",
            "index": 0,
            "_raw": {"title": "第一章", "url": "/chapter/1"},
        }
    ]
