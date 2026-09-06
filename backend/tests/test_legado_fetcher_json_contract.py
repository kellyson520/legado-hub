import json

from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher


def test_toc_chapter_payload_does_not_expose_parser_nodes():
    chapters = [{"title": "第一章", "url": "https://example.test/1", "index": 0, "_raw": object()}]
    safe = LegadoBookSourceFetcher._serialize_chapters(chapters)
    assert safe == [{"title": "第一章", "url": "https://example.test/1", "index": 0}]
    json.dumps(safe)
