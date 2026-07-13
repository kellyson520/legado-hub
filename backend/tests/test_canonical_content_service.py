def test_aligns_source_chapter_by_order_title_and_neighbors(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'canonical-content.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_canonical_content_service

    bootstrap_sqlite()
    service = build_canonical_content_service()
    work = service.create_canonical_work(title='Demo Book', author='Tester')
    service.add_canonical_chapters(work.id, ['Chapter 1', 'Chapter 2'])

    result = service.ingest_source_chapters(
        canonical_work_id=work.id,
        source_id='source-a',
        title='Demo Book',
        author='Tester',
        chapters=[
            {'title': '01 Start', 'chapter_url': 'https://source-a.test/book/1'},
            {'title': '02 Continue', 'chapter_url': 'https://source-a.test/book/2'},
        ],
    )

    assert result.matches[0].confidence >= 0.8
    assert result.matches[0].canonical_index == 0
    assert result.review_items == []


def test_low_confidence_alignment_is_routed_to_review(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'canonical-review.sqlite3'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret-key-32-bytes-minimum')

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.factory import build_canonical_content_service

    bootstrap_sqlite()
    service = build_canonical_content_service()
    work = service.create_canonical_work(title='Demo Book', author='Tester')
    service.add_canonical_chapters(work.id, ['Chapter 1'])

    result = service.ingest_source_chapters(
        canonical_work_id=work.id,
        source_id='source-b',
        title='Demo Book',
        author='Tester',
        chapters=[
            {'title': 'Appendix Mystery', 'chapter_url': 'https://source-b.test/book/a'},
        ],
    )

    assert result.matches[0].review_status == 'review'
    assert result.review_items[0]['source_title'] == 'Appendix Mystery'
