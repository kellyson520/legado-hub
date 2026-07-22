import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.core.response import from_paginated_result, ok
from app.application.services.novel_ingestion_service import NovelIngestionService
from app.infrastructure.persistence.factory import (
    build_novel_agent_service,
    build_novel_repository,
    build_novel_runtime_repository,
    build_source_read_service,
    build_scoped_novel_agent_app_service,
)
from app.infrastructure.novel_ingestion.url_security import NovelUrlPolicy
from app.interfaces.http.deps import (
    owner_scope_for,
    require_principal_permission,
)
from app.interfaces.http.deps import require_permission


router = APIRouter()


class SourceImportRequest(BaseModel):
    source_id: int
    book_url: str = Field(min_length=1, max_length=4000)
    book_name: str = Field(min_length=1, max_length=300)
    author: str = Field(default="", max_length=200)


class UrlImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4000)
    title: str = Field(default="", max_length=300)
    author: str = Field(default="", max_length=200)


class ProgressRequest(BaseModel):
    chapter_id: int
    offset_chars: int = Field(default=0, ge=0)
    percent: float = Field(default=0.0, ge=0.0, le=1.0)
    preferences: dict = Field(default_factory=dict)


class ConversationRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    book_id: int | None = None
    chapter_id: int | None = None
    entrypoint: str = Field(default="workspace", pattern="^(workspace|book|reader)$")
    model: str | None = Field(default=None, max_length=200)


class NovelMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    entrypoint: str = Field(default="workspace", pattern="^(workspace|book|reader)$")
    book_id: int | None = None
    chapter_id: int | None = None
    mode: str = Field(default="chat", pattern="^(chat|character|storyline|world)$")
    model: str | None = Field(default=None, max_length=200)
    stream: bool = False


async def get_scoped_novel_repository():
    return await build_novel_repository()


async def get_novel_ingestion_service():
    repo = await get_scoped_novel_repository()
    return NovelIngestionService(
        repo=repo,
        source_reader=build_source_read_service(),
        runtime_repo=build_novel_runtime_repository(),
        url_policy=NovelUrlPolicy(),
    )


async def get_novel_agent_app_service():
    return await build_scoped_novel_agent_app_service()


def _serialize(value):
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _import_data(result) -> dict:
    return {
        "book_id": result.book_id,
        "duplicate": result.duplicate,
        "status": result.status,
        "task_id": result.task_id,
        "error_code": result.error_code,
    }


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@router.post("/books/import/upload")
async def import_upload(
    file: UploadFile = File(...),
    identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE)),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    service = await get_novel_ingestion_service()
    result = await service.import_upload(
        owner_scope_for(identity),
        file.filename or "novel.txt",
        file.content_type or "application/octet-stream",
        data,
    )
    return {"success": True, "code": "OK", "message": "novel upload queued", "data": _import_data(result), "meta": {}, "trace_id": None}


@router.post("/books/import/source")
async def import_source(payload: SourceImportRequest, identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE))):
    service = await get_novel_ingestion_service()
    result = await service.import_source(
        owner_scope_for(identity), payload.source_id, payload.book_url, payload.book_name, payload.author,
    )
    return {"success": True, "code": "OK", "message": "novel source import queued", "data": _import_data(result), "meta": {}, "trace_id": None}


@router.post("/books/import/url")
async def import_url(payload: UrlImportRequest, identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE))):
    service = await get_novel_ingestion_service()
    result = await service.import_url(owner_scope_for(identity), payload.url, payload.title, payload.author)
    return {"success": True, "code": "OK", "message": "novel URL import queued", "data": _import_data(result), "meta": {}, "trace_id": None}


@router.get("/books")
async def list_books(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=50),
    identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE)),
):
    owner_scope = owner_scope_for(identity)
    repo = await get_scoped_novel_repository()
    books = await repo.list_books(owner_scope, limit=1000, offset=0)
    normalized = search.strip().lower()
    filtered = [
        book for book in books
        if (not normalized or normalized in f"{book.book_name} {book.author} {book.book_url}".lower())
        and (not status or str(getattr(book.status, "value", book.status)) == status)
    ]
    total = len(filtered)
    selected = filtered[(page - 1) * page_size : page * page_size]
    output = []
    for book in selected:
        item = _serialize(book)
        item["progress"] = _serialize(await repo.get_reading_progress(owner_scope, book.id))
        output.append(item)
    result = {
        "items": output,
        "meta": {"page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size},
    }
    return from_paginated_result(result, message="novels listed")

@router.get("/books/{book_id}")
async def get_book(book_id: int, identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE))):
    repo = await get_scoped_novel_repository()
    book = await repo.get_book_by_id(owner_scope_for(identity), book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Novel book not found")
    return {"success": True, "code": "OK", "message": "novel loaded", "data": _serialize(book), "meta": {}, "trace_id": None}


@router.get("/books/{book_id}/chapters")
async def list_chapters(book_id: int, identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE))):
    repo = await get_scoped_novel_repository()
    if await repo.get_book_by_id(owner_scope_for(identity), book_id) is None:
        raise HTTPException(status_code=404, detail="Novel book not found")
    chapters = await repo.get_chapters_by_book(owner_scope_for(identity), book_id, limit=1000)
    return {"success": True, "code": "OK", "message": "chapters listed", "data": [_serialize(item) for item in chapters], "meta": {"total": len(chapters)}, "trace_id": None}


@router.get("/books/{book_id}/chapters/{chapter_id}")
async def get_chapter(book_id: int, chapter_id: int, identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE))):
    repo = await get_scoped_novel_repository()
    chapter = await repo.get_chapter_by_id(owner_scope_for(identity), chapter_id)
    if chapter is None or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="Novel chapter not found")
    return {"success": True, "code": "OK", "message": "chapter loaded", "data": _serialize(chapter), "meta": {}, "trace_id": None}


@router.get("/books/{book_id}/progress")
async def get_progress(book_id: int, identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE))):
    repo = await get_scoped_novel_repository()
    if await repo.get_book_by_id(owner_scope_for(identity), book_id) is None:
        raise HTTPException(status_code=404, detail="Novel book not found")
    progress = await repo.get_reading_progress(owner_scope_for(identity), book_id)
    return {"success": True, "code": "OK", "message": "progress loaded", "data": _serialize(progress), "meta": {}, "trace_id": None}


@router.put("/books/{book_id}/progress")
async def save_progress(book_id: int, payload: ProgressRequest, identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE))):
    service = await get_novel_ingestion_service()
    data = await service.save_progress(owner_scope_for(identity), book_id, payload.chapter_id, payload.offset_chars, payload.percent, payload.preferences)
    return {"success": True, "code": "OK", "message": "progress saved", "data": data, "meta": {}, "trace_id": None}


@router.post("/legacy/claim")
async def claim_legacy_novel_data(identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE))):
    owner_scope = owner_scope_for(identity)
    repo = await get_scoped_novel_repository()
    try:
        books = await repo.claim_legacy_scope(owner_scope)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    runtime = build_novel_runtime_repository()
    runtime_data = runtime.claim_legacy_scope(owner_scope)
    data = {**books, **runtime_data}
    return {"success": True, "code": "OK", "message": "legacy novel data claimed", "data": data, "meta": {}, "trace_id": None}


@router.get("/books/{book_id}/knowledge/{kind}")
async def get_knowledge(book_id: int, kind: str, identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE))):
    owner_scope = owner_scope_for(identity)
    repo = await get_scoped_novel_repository()
    if await repo.get_book_by_id(owner_scope, book_id) is None:
        raise HTTPException(status_code=404, detail="Novel book not found")
    methods = {
        "entities": ("list_entities", {"limit": 500}),
        "relationships": ("get_relationships_by_book", {"limit": 500}),
        "events": ("get_events", {"limit": 500}),
        "state_changes": ("get_state_changes", {"limit": 500}),
    }
    if kind not in methods:
        raise HTTPException(status_code=400, detail="unsupported knowledge kind")
    method_name, kwargs = methods[kind]
    items = await getattr(repo, method_name)(owner_scope, book_id, **kwargs)
    return {"success": True, "code": "OK", "message": "knowledge loaded", "data": [_serialize(item) for item in items], "meta": {"total": len(items)}, "trace_id": None}


@router.post("/conversations")
async def create_novel_conversation(payload: ConversationRequest, identity=Depends(require_principal_permission(Permission.AI_RUN))):
    service = await get_novel_agent_app_service()
    data = await service.create_conversation(
        owner_scope_for(identity),
        payload.title,
        book_id=payload.book_id,
        chapter_id=payload.chapter_id,
        entrypoint=payload.entrypoint,
        model_ref=payload.model,
    )
    return {"success": True, "code": "OK", "message": "novel conversation created", "data": data, "meta": {}, "trace_id": None}


@router.get("/conversations/{conversation_id}")
async def get_novel_conversation(conversation_id: str, identity=Depends(require_principal_permission(Permission.AI_RUN))):
    service = await get_novel_agent_app_service()
    return {"success": True, "code": "OK", "message": "novel conversation loaded", "data": service.get_conversation(owner_scope_for(identity), conversation_id), "meta": {}, "trace_id": None}


@router.post("/conversations/{conversation_id}/messages")
async def send_novel_message(conversation_id: str, payload: NovelMessageRequest, identity=Depends(require_principal_permission(Permission.AI_RUN))):
    service = await get_novel_agent_app_service()
    result = await service.send_message(owner_scope_for(identity), conversation_id, payload.content, entrypoint=payload.entrypoint, book_id=payload.book_id, chapter_id=payload.chapter_id, mode=payload.mode, request_model=payload.model, stream=payload.stream)
    if payload.stream:
        from fastapi.responses import StreamingResponse

        async def events():
            yield "event: started\ndata: {}\n\n"
            async for delta in result:
                yield "event: delta\ndata: " + _json_dumps({"text": delta}) + "\n\n"
            yield "event: completed\ndata: {}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")
    return {"success": True, "code": "OK", "message": "novel message completed", "data": result, "meta": {}, "trace_id": None}


@router.get("/models")
async def list_novel_models(identity=Depends(require_principal_permission(Permission.AI_RUN))):
    del identity
    from app.infrastructure.persistence.factory import build_provider_registry

    groups = {}
    registry = build_provider_registry()
    for group in ("novel_chat", "novel_extract", "novel_summary", "novel_embedding"):
        try:
            groups[group] = [{"model": item.model, "provider": item.provider.name} for item in registry.resolve_group(group)]
        except Exception:
            groups[group] = []
    return {"success": True, "code": "OK", "message": "novel models listed", "data": groups, "meta": {}, "trace_id": None}


@router.get("/tools")
async def list_novel_tools(identity=Depends(require_principal_permission(Permission.AI_RUN)), book_id: int | None = None):
    service = await get_novel_agent_app_service()
    data = await service.list_tools(owner_scope_for(identity), book_id)
    return {"success": True, "code": "OK", "message": "novel tools listed", "data": data, "meta": {"total": len(data)}, "trace_id": None}


@router.post("/books/{novel_id}/analysis")
async def analyze_book(novel_id: str, identity=Depends(require_permission(Permission.NOVEL_MANAGE))):
    service = build_novel_agent_service()
    task = await service.start_analysis(
        novel_id,
        actor_id=str(identity.user_id),
        owner_scope=owner_scope_for(identity),
    )
    return ok(data=task, message="novel analysis queued", meta={})
