from fastapi.testclient import TestClient


def _client_and_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "regex-test.sqlite3"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-bytes-minimum")
    from app.core.security import create_access_token
    from app.main import app

    token = create_access_token({"sub": "1", "permissions": ["engine.test"], "sid": "regex-test"})
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_regex_test_returns_matches_groups_and_javascript_replacement_preview(tmp_path, monkeypatch):
    client, headers = _client_and_headers(tmp_path, monkeypatch)
    response = client.post(
        "/api/engine/regex-test",
        json={"text": "第12章：开始", "pattern": r"第(\d+)章", "replacement": "章节$1"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["match_count"] == 1
    assert data["matches"] == [{"match": "第12章", "groups": ["12"], "span": [0, 4]}]
    assert data["replacement_preview"] == "章节12：开始"
    assert data["error"] is None


def test_regex_test_returns_structured_error_for_invalid_pattern(tmp_path, monkeypatch):
    client, headers = _client_and_headers(tmp_path, monkeypatch)
    response = client.post(
        "/api/engine/regex-test",
        json={"text": "anything", "pattern": "(", "replacement": None},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["match_count"] == 0
    assert data["matches"] == []
    assert data["replacement_preview"] is None
    assert data["error"]
