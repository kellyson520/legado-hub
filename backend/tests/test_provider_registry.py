def test_configured_provider_bootstraps_the_novel_agent_route_groups(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provider-registry.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    monkeypatch.delenv("LLM_API_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    from app.infrastructure.persistence.factory import build_provider_registry
    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.provider_repo_impl import SQLiteProviderRepository

    bootstrap_sqlite()
    account = SQLiteProviderRepository().save_provider(
        name="configured-openai",
        base_url="https://api.example.test/v1",
        api_key="sk-test",
        default_model="gpt-test",
        enabled=True,
    )
    bootstrap_sqlite()

    selection = build_provider_registry().resolve_group("novel_extract")[0]

    assert selection.name == account.name
    assert selection.model == "gpt-test"
