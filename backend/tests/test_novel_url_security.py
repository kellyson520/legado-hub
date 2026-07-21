from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import httpx

from app.services.novel_ingestion.parsers import NovelDocumentParser, UnsafeNovelArchive
from app.services.novel_ingestion.url_security import NovelUrlPolicy, NovelUrlSecurityError


def test_url_policy_rejects_private_and_credentialed_urls():
    policy = NovelUrlPolicy()

    for url in (
        "http://127.0.0.1/book",
        "http://localhost/book",
        "http://169.254.169.254/latest/meta-data",
        "https://user:password@example.com/book",
        "file:///etc/passwd",
    ):
        with pytest.raises(NovelUrlSecurityError):
            policy.validate(url)


def test_epub_rejects_parent_traversal_entries():
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("../chapter.xhtml", "<h1>坏章</h1>")

    with pytest.raises(UnsafeNovelArchive):
        NovelDocumentParser().parse(
            "malicious.epub", "application/epub+zip", buffer.getvalue()
        )


@pytest.mark.asyncio
async def test_fetch_revalidates_redirect_and_response_size(monkeypatch):
    def fake_getaddrinfo(host, port, type):
        return [(None, None, None, None, ("93.184.216.34", port))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/redirect":
            return httpx.Response(
                302,
                headers={"location": "http://127.0.0.1/private"},
                request=request,
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"0123456789",
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    try:
        policy = NovelUrlPolicy(client=client, max_bytes=4)
        with pytest.raises(NovelUrlSecurityError):
            await policy.fetch("https://public.test/redirect")
        with pytest.raises(NovelUrlSecurityError):
            await policy.fetch("https://public.test/too-large")
    finally:
        await client.aclose()
