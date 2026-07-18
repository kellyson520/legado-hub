async def test_quota_repository_keeps_maximum_observed_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.quota_usage_repo_impl import SQLiteQuotaUsageRepository
    from app.infrastructure.persistence.sqlite.schema import ApiKeyModel
    from app.infrastructure.persistence.sqlite.session import SessionLocal

    bootstrap_sqlite()
    db = SessionLocal()
    try:
        key = ApiKeyModel(name="quota-key", key_hash="hash", is_enabled=True)
        db.add(key)
        db.commit()
        key_id = key.id
    finally:
        db.close()

    repo = SQLiteQuotaUsageRepository()
    await repo.upsert_max_usage(
        api_key_id=key_id,
        date="2026-07-19",
        fetch_count=10,
        ai_chars=20,
        storage_mb=1.5,
    )
    await repo.upsert_max_usage(
        api_key_id=key_id,
        date="2026-07-19",
        fetch_count=5,
        ai_chars=30,
        storage_mb=1.0,
    )

    db = SessionLocal()
    try:
        from app.infrastructure.persistence.sqlite.schema import QuotaUsageModel

        usage = db.query(QuotaUsageModel).filter(QuotaUsageModel.api_key_id == key_id).one()
        assert (usage.fetch_count, usage.ai_chars, usage.storage_mb) == (10, 30, 1.5)
    finally:
        db.close()
