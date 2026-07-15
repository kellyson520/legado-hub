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


def test_provider_repository_preserves_blank_edit_key_and_orders_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provider-routing.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.provider_repo_impl import SQLiteProviderRepository

    bootstrap_sqlite()
    repo = SQLiteProviderRepository()
    primary = repo.save_provider(
        name="primary",
        base_url="https://a.example/v1",
        api_key="sk-primary",
        default_model="a-model",
        enabled=True,
    )
    backup = repo.save_provider(
        name="backup",
        base_url="https://b.example/v1",
        api_key="sk-backup",
        default_model="b-model",
        enabled=True,
    )

    edited = repo.save_provider(
        id=primary.id,
        name="primary-renamed",
        base_url="https://a2.example/v1",
        api_key="",
        default_model="a-model-2",
        enabled=False,
    )
    routes = repo.replace_routes(
        "source_build",
        [
            {"provider_account_id": backup.id, "model": "b-model"},
            {"provider_account_id": primary.id, "model": "a-model-2"},
        ],
    )

    assert edited.api_key == "sk-primary"
    assert edited.name == "primary-renamed"
    assert edited.enabled is False
    assert [(item.provider_account_id, item.priority) for item in routes] == [
        (backup.id, 0),
        (primary.id, 1),
    ]
