from dataclasses import dataclass

import pytest


@dataclass
class FakeResponse:
    url: str
    status: int
    text: str
    elapsed_ms: int = 10
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None and 200 <= self.status < 400


class FakeHttpRuntime:
    def __init__(self, responses: dict[str, FakeResponse]):
        self.responses = responses

    async def get(self, url: str, **kwargs) -> FakeResponse:
        return self.responses[url]


@pytest.fixture
def fake_http_runtime():
    return FakeHttpRuntime(
        {
            "https://example.com/search?q=demo": FakeResponse(
                url="https://example.com/search?q=demo",
                status=200,
                text="""
                <div class='book'>
                    <a class='name' href='https://example.com/book/1'>Book A</a>
                </div>
                """,
            ),
            "https://example.com/book/1": FakeResponse(
                url="https://example.com/book/1",
                status=200,
                text="""
                <div class='chapter-list'>
                    <a class='chapter' href='https://example.com/book/1/ch1'>Chapter 1</a>
                </div>
                """,
            ),
            "https://example.com/book/1/ch1": FakeResponse(
                url="https://example.com/book/1/ch1",
                status=200,
                text="<div id='content'>Hello Chapter</div>",
            ),
            "https://example.com/feed.xml": FakeResponse(
                url="https://example.com/feed.xml",
                status=200,
                text="""
                <rss><channel><item><title>News A</title><link>https://example.com/news/1</link></item></channel></rss>
                """,
            ),
        }
    )


@pytest.mark.asyncio
async def test_book_adapter_records_search_toc_and_content_steps(fake_http_runtime):
    from app.infrastructure.legado.engine.source_adapters import BookSourceAdapter

    adapter = BookSourceAdapter(fake_http_runtime)
    result = await adapter.run(
        source={
            "searchUrl": "https://example.com/search?q={{keyword}}",
            "ruleSearch": {"bookList": ".book", "name": ".name", "bookUrl": ".name@href"},
            "ruleToc": {"chapterList": ".chapter", "chapterUrl": "@href"},
            "ruleContent": {"content": "#content"},
        },
        keyword="demo",
    )
    assert list(result.step_results) == ["search", "toc", "content"]
    assert result.step_results["search"]["passed"] is True
    assert result.step_results["toc"]["passed"] is True
    assert result.step_results["content"]["passed"] is True


@pytest.mark.asyncio
async def test_rss_adapter_records_feed_steps(fake_http_runtime):
    from app.infrastructure.legado.engine.source_adapters import RssSourceAdapter

    adapter = RssSourceAdapter(fake_http_runtime)
    result = await adapter.run(source={"sourceUrl": "https://example.com/feed.xml", "ruleArticles": "item"})
    assert result.step_results["feed_fetch"]["passed"] is True
    assert result.step_results["item_parse"]["passed"] is True
