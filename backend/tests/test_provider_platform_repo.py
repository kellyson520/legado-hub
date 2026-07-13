def test_create_provider_account_model_and_quota(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provider-platform.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.provider_repo_impl import SQLiteProviderRepository

    bootstrap_sqlite()
    repo = SQLiteProviderRepository()
    provider = repo.create_provider_account(
        name="primary-openai",
        provider_type="openai_compatible",
        base_url="https://api.example.com",
    )
    model = repo.create_model(provider.id, name="gpt-4.1-mini", capabilities=["chat", "json"])
    quota = repo.create_quota_policy(scope_type="user", scope_id="admin", daily_cost_limit=50)

    assert model.provider_account_id == provider.id
    assert quota.scope_id == "admin"
