from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.application.services.ai_service import AIService
from app.core.exceptions import NotFoundException, ValidationException
from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage
from app.domain.entities.auth import AuditEvent


_SENSITIVE_KEY_PARTS = ("cookie", "token", "authorization", "provider", "internal", "api_key", "apikey")
MODE_PROMPTS = {
    "chat": "使用中文回答阅读、书源和小说相关问题。",
    "character": "使用中文分析人物动机、关系、性格和证据。",
    "storyline": "使用中文梳理剧情、冲突、转折和时间线。",
    "world": "使用中文说明世界观、势力、设定和规则。",
}


class _ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict = {}


class _EmptyArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _SourceVersionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_version_id: str


class AIWorkspaceService:
    def __init__(self, platform, conversations, sources, ai_tasks, audit):
        self._platform = platform
        self._conversations = conversations
        self._sources = sources
        self._ai_tasks = ai_tasks
        self._audit = audit

    async def create_conversation(self, actor_id: str, title: str = "") -> dict:
        conversation = self._conversations.create_conversation(
            AIConversation(id=uuid4().hex, actor_id=str(actor_id), title=title.strip() or "新对话")
        )
        await self._audit_event(actor_id, "ai.conversation.create", conversation.id)
        return self._serialize_conversation(conversation)

    async def list_conversations(self, actor_id: str) -> list[dict]:
        return [self._serialize_conversation(item) for item in self._conversations.list_conversations(str(actor_id))]

    def get_conversation(self, conversation_id: str, actor_id: str) -> dict:
        conversation = self._conversations.get_conversation(conversation_id, str(actor_id))
        if conversation is None:
            raise NotFoundException("AI conversation not found")
        return {
            **self._serialize_conversation(conversation),
            "messages": [self._serialize_message(item) for item in self._conversations.list_messages(conversation.id)],
        }

    async def send_message(
        self,
        conversation_id: str,
        actor_id: str,
        mode: str,
        content: str,
        tool_requests: list[dict] | None = None,
        source_version_id: str | None = None,
    ) -> dict:
        if mode not in MODE_PROMPTS:
            raise ValidationException("Unsupported AI mode")
        if not content.strip():
            raise ValidationException("Message content is required")
        conversation = self._conversations.get_conversation(conversation_id, str(actor_id))
        if conversation is None:
            raise NotFoundException("AI conversation not found")

        user_message = self._conversations.append_message(
            AIConversationMessage(
                id=uuid4().hex,
                conversation_id=conversation.id,
                role="user",
                mode=mode,
                content=content.strip(),
            )
        )
        tool_calls = await self._execute_tools(actor_id, tool_requests or [])
        payload = {
            "task": "ai_workspace",
            "mode": mode,
            "source_version_id": source_version_id,
            "tool_results": tool_calls,
            "messages": [
                {"role": "system", "content": MODE_PROMPTS[mode]},
                {"role": "user", "content": user_message.content},
            ],
        }
        try:
            invocation = await self._platform.invoke_chat(
                provider_group="ai",
                model="gpt-4.1-mini",
                payload=payload,
                quota_scope=("user", str(actor_id)),
            )
            output = invocation.get("output")
            assistant_content = output.get("text", "") if isinstance(output, dict) else str(output or "")
            assistant = self._conversations.append_message(
                AIConversationMessage(
                    id=uuid4().hex,
                    conversation_id=conversation.id,
                    role="assistant",
                    mode=mode,
                    content=assistant_content,
                    tool_calls=tool_calls,
                )
            )
        except Exception as exc:
            assistant = self._conversations.append_message(
                AIConversationMessage(
                    id=uuid4().hex,
                    conversation_id=conversation.id,
                    role="assistant",
                    mode=mode,
                    content=AIService._sanitize_error(exc),
                    status="failed",
                    tool_calls=tool_calls,
                )
            )
        await self._audit_event(actor_id, "ai.conversation.message", conversation.id)
        return self._serialize_message(assistant)

    async def _execute_tools(self, actor_id: str, tool_requests: list[dict]) -> list[dict]:
        calls: list[dict] = []
        for raw_request in tool_requests:
            request = _ToolRequest.model_validate(raw_request)
            if request.name == "list_visible_sources":
                _EmptyArguments.model_validate(request.arguments)
                result = self._list_visible_sources(str(actor_id))
            elif request.name == "get_source_rule_summary":
                args = _SourceVersionArguments.model_validate(request.arguments)
                result = self._get_source_rule_summary(args.source_version_id, str(actor_id))
            elif request.name == "list_ai_analysis_results":
                _EmptyArguments.model_validate(request.arguments)
                result = self._list_ai_results(str(actor_id))
            else:
                raise ValidationException("Unsupported AI tool")
            sanitized = _sanitize(result)
            calls.append({"name": request.name, "arguments": request.arguments, "result": sanitized})
            await self._audit_event(actor_id, "ai.tool.invoke", request.name)
        return calls

    def _list_visible_sources(self, actor_id: str) -> list[dict]:
        rows = self._sources.list_recent_versions(limit=50)
        return [
            {
                "id": row.id,
                "name": row.payload.get("bookSourceName", row.source_id),
                "url": row.payload.get("bookSourceUrl", row.source_id),
                "status": row.status,
            }
            for row in rows
            if row.status == "published" or str(row.created_by) == actor_id
        ]

    def _get_source_rule_summary(self, source_version_id: str, actor_id: str) -> dict:
        version = self._sources.get_version(source_version_id)
        if version is None or (version.status != "published" and str(version.created_by) != actor_id):
            raise NotFoundException("Source version not found")
        return {
            "id": version.id,
            "source_id": version.source_id,
            "status": version.status,
            "rules": {key: version.payload.get(key) for key in ("ruleSearch", "ruleBookInfo", "ruleToc", "ruleContent")},
        }

    def _list_ai_results(self, actor_id: str) -> list[dict]:
        return [
            {"id": task.id, "type": task.kind, "status": task.status, "result": task.result}
            for task in self._ai_tasks.list_tasks()
            if str(task.actor_id) == actor_id
        ]

    async def _audit_event(self, actor_id: str, action: str, resource: str) -> None:
        await self._audit.record_audit(AuditEvent(actor_id=int(actor_id), action=action, resource="ai_conversation", detail=resource))

    @staticmethod
    def _serialize_conversation(item: AIConversation) -> dict:
        return {"id": item.id, "title": item.title, "created_at": item.created_at.isoformat()}

    @staticmethod
    def _serialize_message(item: AIConversationMessage) -> dict:
        return {
            "id": item.id,
            "role": item.role,
            "mode": item.mode,
            "content": item.content,
            "status": item.status,
            "tool_calls": item.tool_calls,
            "created_at": item.created_at.isoformat(),
        }


def _sanitize(value):
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _sanitize(item)
        for key, item in value.items()
        if not any(part in key.lower() for part in _SENSITIVE_KEY_PARTS)
    }
