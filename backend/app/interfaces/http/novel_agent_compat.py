"""Thin compatibility routes for clients using the original novel-agent API."""

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.interfaces.http import novel as novel_http
from app.interfaces.http.deps import owner_scope_for, require_principal_permission


compat_router = APIRouter(prefix="/api/v1/novel-agent")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    conversation_id: str | None = None
    book_id: int | None = None
    chapter_id: int | None = None
    entrypoint: str = Field(default="workspace", pattern="^(workspace|book|reader)$")
    mode: str = Field(default="chat", pattern="^(chat|character|storyline|world)$")
    model: str | None = Field(default=None, max_length=200)


def _import_data(result) -> dict:
    return {
        "book_id": result.book_id,
        "duplicate": result.duplicate,
        "status": result.status,
        "task_id": result.task_id,
        "error_code": result.error_code,
    }


@compat_router.post("/import/upload")
async def import_upload(
    file: UploadFile = File(...),
    identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE)),
):
    return await novel_http.import_upload(file, identity)


@compat_router.post("/import/source")
async def import_source(
    payload: novel_http.SourceImportRequest,
    identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE)),
):
    return await novel_http.import_source(payload, identity)


@compat_router.post("/import/url")
async def import_url(
    payload: novel_http.UrlImportRequest,
    identity=Depends(require_principal_permission(Permission.NOVEL_MANAGE)),
):
    return await novel_http.import_url(payload, identity)


@compat_router.post("/chat")
async def chat(
    payload: ChatRequest,
    identity=Depends(require_principal_permission(Permission.AI_RUN)),
):
    owner_scope = owner_scope_for(identity)
    service = await novel_http.get_novel_agent_app_service()
    conversation_id = payload.conversation_id
    if not conversation_id:
        conversation = await service.create_conversation(
            owner_scope,
            "阅读助手",
            book_id=payload.book_id,
            chapter_id=payload.chapter_id,
            entrypoint=payload.entrypoint,
            model_ref=payload.model,
        )
        conversation_id = conversation["id"]
    result = await service.send_message(
        owner_scope,
        conversation_id,
        payload.message,
        entrypoint=payload.entrypoint,
        book_id=payload.book_id,
        chapter_id=payload.chapter_id,
        mode=payload.mode,
        request_model=payload.model,
    )
    answer = result.get("content", result.get("answer", "")) if isinstance(result, dict) else str(result)
    return {"success": True, "code": "OK", "message": "novel chat completed", "data": {"answer": answer, **(result if isinstance(result, dict) else {})}, "meta": {}, "trace_id": None}
