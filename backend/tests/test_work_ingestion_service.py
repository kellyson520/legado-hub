from types import SimpleNamespace

import pytest


class FakeReader:
    async def search_books(self, keyword, source_ids=None, limit_per_source=3, author_hint=None):
        return {
            "keyword": keyword,
            "items": [{
                "source_id": 7,
                "name": keyword,
                "author": author_hint or "作者",
                "bookUrl": "https://source.test/book/1",
            }],
        }

    async def get_book_toc(self, source_id, book_url, book_name, author_hint):
        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "book_url": book_url,
            "chapters": [{"title": "第一章 入世", "url": book_url + "/chapter-1"}],
            "fallback_used": False,
        }

    async def get_chapter_content(self, source_id, chapter_url, book_name, author_hint, chapter_title, chapter_index):
        return {
            "source_id": source_id,
            "resolved_source_id": source_id,
            "chapter_url": chapter_url,
            "content": "宁姚看向少年。山门外下起了雨。",
            "title": chapter_title,
            "fallback_used": False,
        }


class FakeSourceRepository:
    async def list_book_sources_full(self, enabled_only=False, ids=None, urls=None):
        sources = [{
            "id": 7,
            "bookSourceName": "健康测试源",
            "bookSourceUrl": "https://source.test",
            "enabled": True,
        }]
        return [source for source in sources if ids is None or source["id"] in ids]


class FakeSourceRuntimeRepository:
    def list_published_versions(self):
        return [SimpleNamespace(
            source_type="book",
            payload={"bookSourceUrl": "https://source.test"},
        )]


class FakeHealthRepository:
    def get_snapshot(self, source_id):
        return SimpleNamespace(health_status="healthy") if source_id == 7 else None


@pytest.fixture
def ingestion_service(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "work-ingestion.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.evidence_service import EvidenceService
    from app.application.services.work_ingestion_service import WorkIngestionService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.canonical_content_repo_impl import SQLiteCanonicalContentRepository
    from app.infrastructure.persistence.sqlite.evidence_repo_impl import SQLiteEvidenceRepository

    bootstrap_sqlite()
    canonical_repo = SQLiteCanonicalContentRepository()
    return WorkIngestionService(
        reader=FakeReader(),
        source_repo=FakeSourceRepository(),
        source_runtime_repo=FakeSourceRuntimeRepository(),
        source_health_repo=FakeHealthRepository(),
        canonical_repo=canonical_repo,
        evidence_service=EvidenceService(SQLiteEvidenceRepository(), canonical_repo),
    )


@pytest.mark.asyncio
async def test_selected_source_chapter_becomes_canonical_evidence(ingestion_service):
    result = await ingestion_service.fetch_and_ingest_chapter(
        source_id=7,
        book_url="https://source.test/book/1",
        chapter_index=0,
        book_name="测试书",
        author_hint="作者",
    )

    assert result.canonical_work_id
    assert result.content_variant_id
    assert result.evidence_span_ids
