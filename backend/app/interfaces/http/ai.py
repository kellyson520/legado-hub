from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_ai_service, build_ai_workspace_service
from app.infrastructure.persistence.factory import build_system_settings_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


class CharacterAnalysisRequest(BaseModel):
    title: str
    content: str


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)


class ConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    mode: str = Field(default="chat", pattern="^(chat|character|storyline|world)$")
    tool_requests: list[dict] = Field(default_factory=list)
    source_version_id: str | None = Field(default=None, max_length=100)


def _workspace_tool_names(identity) -> set[str]:
    names = {"list_ai_analysis_results"}
    if Permission.BOOK_SOURCES_READ.value in identity.permissions:
        names.update({
            "list_visible_sources",
            "get_source_rule_summary",
            "get_source_validation_summary",
        })
    source_agent_settings = build_system_settings_service().get_source_build_agent_settings()
    if (
        Permission.BOOK_SOURCES_READ.value in identity.permissions
        and Permission.BOOK_SOURCES_WRITE.value in identity.permissions
        and source_agent_settings["enabled"]
        and source_agent_settings["provider_configured"]
    ):
        names.add("create_source_rule_draft")
    return names


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
async def list_conversations(identity=Depends(require_permission(Permission.AI_RUN))):
    data = await build_ai_workspace_service().list_conversations(str(identity.user_id))
    return {"success": True, "code": "OK", "message": "ai conversations listed", "data": data, "meta": {"total": len(data)}, "trace_id": None}


@router.post("/conversations")
async def create_conversation(
    payload: ConversationCreateRequest,
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    data = await build_ai_workspace_service().create_conversation(str(identity.user_id), payload.title)
    return {"success": True, "code": "OK", "message": "ai conversation created", "data": data, "meta": {}, "trace_id": None}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    data = build_ai_workspace_service().get_conversation(conversation_id, str(identity.user_id))
    return {"success": True, "code": "OK", "message": "ai conversation loaded", "data": data, "meta": {}, "trace_id": None}


@router.post("/conversations/{conversation_id}/messages")
async def send_conversation_message(
    conversation_id: str,
    payload: ConversationMessageRequest,
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    data = await build_ai_workspace_service().send_message(
        conversation_id=conversation_id,
        actor_id=str(identity.user_id),
        mode=payload.mode,
        content=payload.content,
        tool_requests=payload.tool_requests,
        source_version_id=payload.source_version_id,
        allowed_tool_names=_workspace_tool_names(identity),
    )
    return {"success": True, "code": "OK", "message": "ai conversation message completed", "data": data, "meta": {}, "trace_id": None}
