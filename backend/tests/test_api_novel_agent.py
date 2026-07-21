from dataclasses import dataclass

from fastapi.testclient import TestClient


def _headers(user_id: int, permissions: list[str]):
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id), 'permissions': permissions})}"}


@dataclass
class Book:
    id: int = 7
    book_name: str = "测试书"
    author: str = "作者"
    book_url: str = "upload:test"
    source_name: str = "上传"
    total_chapters: int = 1
    total_words: int = 20
    ingest_progress: float = 0.3
    status: str = "summarizing"
    summary_global: str = ""


class NovelRepo:
    async def list_books(self, owner_scope, **_kwargs):
        return [Book()] if owner_scope == "user:1" else []

    async def count_books(self, owner_scope, **_kwargs):
        return 1 if owner_scope == "user:1" else 0

    async def get_book_by_id(self, owner_scope, book_id):
        return Book() if owner_scope == "user:1" and book_id == 7 else None

    async def get_chapters_by_book(self, owner_scope, book_id, **_kwargs):
        return [] if owner_scope == "user:1" and book_id == 7 else []

    async def get_reading_progress(self, owner_scope, book_id):
        return None


class Ingestion:
    async def import_upload(self, owner_scope, filename, media_type, data, **_kwargs):
        assert owner_scope == "user:1"
        return type("ImportResult", (), {"book_id": 7, "duplicate": False, "status": "queued", "task_id": "task-1", "error_code": None})()


class Agent:
    async def create_conversation(self, owner_scope, title="", **kwargs):
        return {"id": "conversation-1", "owner_scope": owner_scope, "title": title, **kwargs, "messages": []}

    def get_conversation(self, owner_scope, conversation_id):
        return {"id": conversation_id, "owner_scope": owner_scope, "messages": []}

    async def send_message(self, owner_scope, conversation_id, content, **kwargs):
        return {"content": "答案", "tool_calls": [], "owner_scope": owner_scope, "conversation_id": conversation_id, **kwargs}

    async def list_tools(self, owner_scope, book_id=None):
        return [{"name": "chapter.search", "category": "read", "book_id": book_id}]


def test_upload_is_scoped_and_legacy_chat_still_works(monkeypatch):
    from app.interfaces.http import novel as novel_http
    from app.interfaces.api.v1 import novel_agent as novel_agent_api

    monkeypatch.setattr(novel_http, "get_scoped_novel_repository", lambda: _async_value(NovelRepo()))
    monkeypatch.setattr(novel_http, "get_novel_ingestion_service", lambda: _async_value(Ingestion()))
    monkeypatch.setattr(novel_agent_api, "build_novel_agent_app_service", lambda: Agent())

    from app.main import app

    client = TestClient(app)
    owner = _headers(1, ["ai.run", "novel.manage"])
    other = _headers(2, ["ai.run", "novel.manage"])

    created = client.post(
        "/api/v1/novel-agent/import/upload",
        headers=owner,
        files={"file": ("a.txt", "第一章\n甲".encode(), "text/plain")},
    )
    assert created.status_code == 200
    assert created.json()["data"]["book_id"] == 7
    assert client.get("/api/novel/books/7", headers=other).status_code == 404

    response = client.post(
        "/api/v1/novel-agent/chat",
        headers=owner,
        json={"message": "林远是谁"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["answer"] == "答案"


async def _async_value(value):
    return value


def test_missing_novel_permission_is_rejected(monkeypatch):
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/novel/books", headers=_headers(1, ["ai.run"]))

    assert response.status_code == 403
