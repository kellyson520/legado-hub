import inspect
import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.core.response import from_paginated_result, ok
from app.infrastructure.persistence.factory import (
    build_ai_service,
    build_ai_conversation_service,
    build_ai_workspace_service,
    build_scoped_novel_agent_app_service,
)
from app.infrastructure.persistence.factory import build_system_settings_service
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


class AuthorizationDecisionRequest(BaseModel):
    decision: Literal["once", "conversation", "remember", "deny"]


def _workspace_tool_names(identity) -> set[str]:
    names = {"list_ai_analysis_results"}
    if Permission.BOOK_SOURCES_READ.value in identity.permissions:
        names.update({
            "list_visible_sources",
            "get_source_rule_summary",
            "get_source_validation_summary",
            "source.search",
            "toc.get",
            "chapter.fetch",
        })
    source_agent_settings = build_system_settings_service().get_source_build_agent_settings()
    if (
        Permission.BOOK_SOURCES_READ.value in identity.permissions
        and Permission.BOOK_SOURCES_WRITE.value in identity.permissions
        and source_agent_settings["enabled"]
        and source_agent_settings["provider_configured"]
    ):
        names.update({"create_source_rule_draft", "source.joint_test"})
    return names


def _principal_actor_id(identity) -> str:
    """Use the same actor key that owner-scoped conversation storage derives."""
    scope = owner_scope_for(identity)
    return scope.split(":", 1)[1] if ":" in scope else scope


@router.get("/tasks")
async def list_ai_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=50),
    _=Depends(require_permission(Permission.AI_RUN)),
):
    service = build_ai_service()
    result = await service.list_tasks_page(page=page, page_size=page_size, search=search, status=status)
    return from_paginated_result(result, message="ai tasks listed")


@router.post("/tasks/character")
async def run_character_analysis(
    payload: CharacterAnalysisRequest,
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    service = build_ai_service()
    task = await service.run_character_analysis(payload.model_dump(), actor_id=str(identity.user_id))
    return ok(data=task, message="ai character analysis queued", meta={})


@router.get("/conversations")
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    identity=Depends(require_principal_permission(Permission.AI_RUN)),
):
    actor_id = _principal_actor_id(identity)
    result = await build_ai_conversation_service().list_conversations_page(
        actor_id,
        page=page,
        page_size=page_size,
        search=search,
        owner_scope=owner_scope_for(identity),
    )
    return from_paginated_result(result, message="ai conversations listed")


@router.post("/conversations")
async def create_conversation(
    payload: ConversationCreateRequest,
    identity=Depends(require_principal_permission(Permission.AI_RUN)),
):
    actor_id = _principal_actor_id(identity)
    data = await build_ai_conversation_service().create_conversation(
        actor_id,
        payload.title,
        owner_scope=owner_scope_for(identity),
        book_id=payload.book_id,
        entrypoint=payload.entrypoint,
        model_ref=payload.model,
    )
    return ok(data=data, message="ai conversation created", meta={})


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    identity=Depends(require_principal_permission(Permission.AI_RUN)),
):
    actor_id = _principal_actor_id(identity)
    data = build_ai_conversation_service().get_conversation(conversation_id, actor_id, owner_scope_for(identity))
    return ok(data=data, message="ai conversation loaded", meta={})


@router.post("/conversations/{conversation_id}/messages")
async def send_conversation_message(
    conversation_id: str,
    payload: ConversationMessageRequest,
    identity=Depends(require_principal_permission(Permission.AI_RUN)),
):
    actor_id = _principal_actor_id(identity)
    bound_book_id = payload.book_id
    bound_chapter_id = payload.chapter_id
    if bound_book_id is None:
        bound_conversation = build_ai_conversation_service().get_conversation(
            conversation_id,
            actor_id,
            owner_scope_for(identity),
        )
        if isinstance(bound_conversation, dict):
            bound_book_id = bound_conversation.get("book_id")
            if bound_chapter_id is None:
                bound_chapter_id = bound_conversation.get("chapter_id")
    if bound_book_id is None:
        workspace = build_ai_workspace_service()
    else:
        workspace = build_ai_workspace_service(
            novel_agent_app=await build_scoped_novel_agent_app_service(),
        )
    data = await workspace.send_message(
        conversation_id=conversation_id,
        actor_id=actor_id,
        mode=payload.mode,
        content=payload.content,
        tool_requests=payload.tool_requests,
        source_version_id=payload.source_version_id,
        allowed_tool_names=_workspace_tool_names(identity),
        owner_scope=owner_scope_for(identity),
        entrypoint=payload.entrypoint,
        book_id=bound_book_id,
        chapter_id=bound_chapter_id,
        request_model=payload.model,
        stream=payload.stream,
    )
    if payload.stream and hasattr(data, "__aiter__"):
        from fastapi.responses import StreamingResponse

        async def events():
            async for event in data:
                if isinstance(event, dict) and event.get("event"):
                    yield (
                        f"event: {event['event']}\n"
                        f"data: {json.dumps(event.get('data', {}), ensure_ascii=False)}\n\n"
                    )
                else:
                    yield "event: delta\ndata: " + json.dumps({"text": str(event)}, ensure_ascii=False) + "\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")
    return ok(data=data, message="ai conversation message completed", meta={})


@router.post("/conversations/{conversation_id}/authorization-requests/{request_id}/decision")
async def decide_authorization(
    conversation_id: str,
    request_id: str,
    payload: AuthorizationDecisionRequest,
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    workspace = build_ai_workspace_service()
    decision_kwargs = {
        "actor_id": str(identity.user_id),
        "conversation_id": conversation_id,
        "decision": payload.decision,
        "rbac_permissions": set(identity.permissions),
    }
    try:
        supports_tool_names = "allowed_tool_names" in inspect.signature(workspace.decide_authorization).parameters
    except (TypeError, ValueError):
        supports_tool_names = True
    if supports_tool_names:
        decision_kwargs["allowed_tool_names"] = _workspace_tool_names(identity)
    data = await workspace.decide_authorization(
        request_id,
        **decision_kwargs,
    )
    return ok(data=data, message="ai authorization decision completed", meta={})


@router.get("/conversations/{conversation_id}/authorization-requests")
async def list_authorization_requests(
    conversation_id: str,
    status: str | None = Query(default="pending", max_length=32),
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    data = [] if status not in (None, "pending") else build_ai_conversation_service().list_pending_authorizations(
        str(identity.user_id), conversation_id,
    )
    return ok(data=data, message="ai authorization requests listed", meta={})


@router.get("/authorization-grants")
async def list_authorization_grants(
    conversation_id: str | None = Query(default=None, max_length=100),
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    data = build_ai_conversation_service().list_authorization_grants(str(identity.user_id), conversation_id)
    return ok(data=data, message="ai authorization grants listed", meta={})


@router.post("/authorization-grants/{grant_id}/revoke")
async def revoke_authorization_grant(
    grant_id: str,
    identity=Depends(require_permission(Permission.AI_RUN)),
):
    data = await build_ai_conversation_service().revoke_authorization_grant(
        grant_id,
        actor_id=str(identity.user_id),
    )
    return ok(data=data, message="ai authorization grant revoked", meta={})
