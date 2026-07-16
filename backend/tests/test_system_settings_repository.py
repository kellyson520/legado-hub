import pytest


def build_repository(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "settings-repository.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")

    from app.infrastructure.persistence.sqlite.bootstrap import bootstrap_sqlite
    from app.infrastructure.persistence.sqlite.system_settings_repo_impl import (
        SQLiteSystemSettingsRepository,
    )

    bootstrap_sqlite()
    return SQLiteSystemSettingsRepository()


def test_json_setting_round_trips_with_a_new_version(monkeypatch, tmp_path):
    repository = build_repository(monkeypatch, tmp_path)

    first = repository.put_json(
        "agents.governance",
        {"enabled": False},
        expected_version=None,
    )
    loaded = repository.get_json(
        "agents.governance",
        default={"enabled": True},
    )
    second = repository.put_json(
        "agents.governance",
        {"enabled": True},
        expected_version=first.version,
    )

    assert loaded.value == {"enabled": False}
    assert second.value == {"enabled": True}
    assert second.version != first.version


def test_json_setting_rejects_a_stale_version(monkeypatch, tmp_path):
    from app.domain.repositories.system_settings_repo import ConcurrentSettingsUpdateError

    repository = build_repository(monkeypatch, tmp_path)
    first = repository.put_json(
        "agents.governance",
        {"enabled": False},
        expected_version=None,
    )
    repository.put_json(
        "agents.governance",
        {"enabled": True},
        expected_version=first.version,
    )

    with pytest.raises(ConcurrentSettingsUpdateError):
        repository.put_json(
            "agents.governance",
            {"enabled": False},
            expected_version=first.version,
        )
