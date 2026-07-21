from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_ai_service, build_ai_workspace_service
from app.interfaces.http.deps import owner_scope_for, require_permission, require_principal_permission


router = APIRouter()


class CharacterAnalysisRequest(BaseModel):
    title: str
    content: str


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    book_id: int | None = None
    entrypoint: str = Field(default="workspace", pattern="^(workspace|book|reader)$")
    model: str | None = Field(default=None, max_length=200)


class ConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    mode: str = Field(default="chat", pattern="^(chat|character|storyline|world)$")
    tool_requests: list[dict] = Field(default_factory=list)
    source_version_id: str | None = Field(default=None, max_length=100)
    entrypoint: str = Field(default="workspace", pattern="^(workspace|book|reader)$")
    book_id: int | None = None
    chapter_id: int | None = None
    model: str | None = Field(default=None, max_length=200)
    stream: bool = False


@router.get("/tasks")
async def list_ai_tasks(_=Depends(require_permission(Permission.AI_RUN))):
    service = build_ai_service()
    tasks = await service.list_tasks()
    return {"success": True, "code": "OK", "message": "ai tasks listed", "data": tasks, "meta": {"total": len(tasks)}, "trace_id": None}


@router.post("/tasks/character")
async def run_character_analysis(
    payload: CharacterAnalysisRequest,
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    service = build_ai_service()
    task = await service.run_character_analysis(payload.model_dump(), actor_id=str(identity.user_id))
    return {"success": True, "code": "OK", "message": "ai character analysis queued", "data": task, "meta": {}, "trace_id": None}


@router.get("/conversations")
async def list_conversations(identity=Depends(require_principal_permission(Permission.AI_RUN))):
    actor_id = str(getattr(identity, "user_id", None) or getattr(identity, "api_key_id"))
    data = await build_ai_workspace_service().list_conversations(actor_id, owner_scope_for(identity))
    return {"success": True, "code": "OK", "message": "ai conversations listed", "data": data, "meta": {"total": len(data)}, "trace_id": None}


@router.post("/conversations")
async def create_conversation(
    payload: ConversationCreateRequest,
    identity=Depends(require_principal_permission(Permission.AI_RUN)),
):
    actor_id = str(getattr(identity, "user_id", None) or getattr(identity, "api_key_id"))
    data = await build_ai_workspace_service().create_conversation(
        actor_id,
        payload.title,
        owner_scope=owner_scope_for(identity),
        book_id=payload.book_id,
        entrypoint=payload.entrypoint,
        model_ref=payload.model,
    )
    return {"success": True, "code": "OK", "message": "ai conversation created", "data": data, "meta": {}, "trace_id": None}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    identity=Depends(require_principal_permission(Permission.AI_RUN)),
):
    actor_id = str(getattr(identity, "user_id", None) or getattr(identity, "api_key_id"))
    data = build_ai_workspace_service().get_conversation(conversation_id, actor_id, owner_scope_for(identity))
    return {"success": True, "code": "OK", "message": "ai conversation loaded", "data": data, "meta": {}, "trace_id": None}


@router.post("/conversations/{conversation_id}/messages")
async def send_conversation_message(
    conversation_id: str,
    payload: ConversationMessageRequest,
    identity=Depends(require_principal_permission(Permission.AI_RUN)),
):
    actor_id = str(getattr(identity, "user_id", None) or getattr(identity, "api_key_id"))
    data = await build_ai_workspace_service().send_message(
        conversation_id=conversation_id,
        actor_id=actor_id,
        mode=payload.mode,
        content=payload.content,
        tool_requests=payload.tool_requests,
        source_version_id=payload.source_version_id,
        owner_scope=owner_scope_for(identity),
        entrypoint=payload.entrypoint,
        book_id=payload.book_id,
        chapter_id=payload.chapter_id,
        request_model=payload.model,
        stream=payload.stream,
    )
    return {"success": True, "code": "OK", "message": "ai conversation message completed", "data": data, "meta": {}, "trace_id": None}
