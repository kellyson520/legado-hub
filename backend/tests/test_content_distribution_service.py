def test_reading_uses_next_healthy_variant_after_primary_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'content-distribution.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import (
        build_canonical_content_service,
        build_content_distribution_service,
    )

    bootstrap_sqlite()
    canonical = build_canonical_content_service()
    distribution = build_content_distribution_service()

    work = canonical.create_canonical_work(title='Demo Book', author='Tester')
    canonical_chapter = canonical.add_canonical_chapters(work.id, ['Chapter 1'])[0]
    source_work = canonical.create_source_work(
        canonical_work_id=work.id,
        source_id='primary-source',
        title='Demo Book',
        author='Tester',
    )
    source_chapter_primary = canonical.add_source_chapter(
        source_work.id,
        title='Chapter 1',
        chapter_url='https://primary.test/book/1',
        chapter_index=0,
    )
    canonical.save_alignment(
        canonical_chapter_id=canonical_chapter.id,
        source_chapter_id=source_chapter_primary.id,
        confidence=1.0,
        evidence={'match': 'exact'},
        review_status='accepted',
    )
    canonical.add_content_variant(
        canonical_chapter_id=canonical_chapter.id,
        source_chapter_id=source_chapter_primary.id,
        source_id='primary-source',
        content='',
        health_status='healthy',
        quality_score=0.95,
        coverage_score=0.95,
        freshness_score=0.8,
        latency_ms=80,
    )

    source_work_alt = canonical.create_source_work(
        canonical_work_id=work.id,
        source_id='healthy-source',
        title='Demo Book',
        author='Tester',
    )
    source_chapter_alt = canonical.add_source_chapter(
        source_work_alt.id,
        title='Chapter 1',
        chapter_url='https://healthy.test/book/1',
        chapter_index=0,
    )
    canonical.save_alignment(
        canonical_chapter_id=canonical_chapter.id,
        source_chapter_id=source_chapter_alt.id,
        confidence=1.0,
        evidence={'match': 'exact'},
        review_status='accepted',
    )
    canonical.add_content_variant(
        canonical_chapter_id=canonical_chapter.id,
        source_chapter_id=source_chapter_alt.id,
        source_id='healthy-source',
        content='正文内容',
        health_status='healthy',
        quality_score=0.9,
        coverage_score=0.9,
        freshness_score=0.9,
        latency_ms=40,
    )

    result = distribution.read_chapter(tenant_id='t1', chapter_id=canonical_chapter.id)

    assert result['route_summary']['fallback_count'] == 1
    assert result['result']['source_id'] == 'healthy-source'
    assert result['result']['content'] == '正文内容'
