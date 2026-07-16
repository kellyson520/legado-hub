import pytest


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "evidence.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.application.services.evidence_service import EvidenceService
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.canonical_content_repo_impl import (
        SQLiteCanonicalContentRepository,
    )
    from app.infrastructure.persistence.sqlite.evidence_repo_impl import SQLiteEvidenceRepository

    bootstrap_sqlite()
    canonical_repo = SQLiteCanonicalContentRepository()
    work = canonical_repo.create_canonical_work(title="测试书", author="作者")
    chapter = canonical_repo.add_canonical_chapter(
        canonical_work_id=work.id,
        chapter_index=0,
        title="第一章",
    )
    source_work = canonical_repo.create_source_work(
        canonical_work_id=work.id,
        source_id="source-1",
        title="测试书",
        author="作者",
    )
    source_chapter = canonical_repo.add_source_chapter(
        source_work_id=source_work.id,
        chapter_index=0,
        title="第一章",
        chapter_url="https://source.test/book/1",
        canonical_chapter_id=chapter.id,
    )
    variant = canonical_repo.add_content_variant(
        canonical_chapter_id=chapter.id,
        source_chapter_id=source_chapter.id,
        source_id="source-1",
        content="甲。乙。丙。",
        health_status="healthy",
        quality_score=1,
        coverage_score=1,
        freshness_score=1,
        latency_ms=1,
        is_verified=True,
    )
    return EvidenceService(SQLiteEvidenceRepository(), canonical_repo), chapter, variant, canonical_repo


def test_span_creation_is_hashed_and_non_overlapping(service):
    evidence_service, chapter, variant, _ = service

    spans = evidence_service.create_spans(
        content_variant_id=variant.id,
        canonical_chapter_id=chapter.id,
        content="甲。乙。丙。",
        max_chars=3,
    )

    assert [span.excerpt for span in spans] == ["甲。", "乙。", "丙。"]
    assert all(span.content_sha256 for span in spans)
    assert spans[0].end_offset <= spans[1].start_offset


def test_verified_span_is_unavailable_when_variant_content_changes(service):
    evidence_service, chapter, variant, canonical_repo = service
    span = evidence_service.create_spans(
        content_variant_id=variant.id,
        canonical_chapter_id=chapter.id,
        content="证据正文",
        max_chars=100,
    )[0]

    canonical_repo.replace_content_variant_content(variant.id, "已变化正文")

    assert evidence_service.get_verified_span(span.id) is None
