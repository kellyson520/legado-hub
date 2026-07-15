import json
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.application.services.ai_service import AIService
from app.core.exceptions import NotFoundException, ValidationException
from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage
from app.domain.entities.auth import AuditEvent


_SENSITIVE_KEY_PARTS = ("cookie", "token", "authorization", "provider", "internal", "api_key", "apikey")
_MAX_MODEL_TOOL_TURNS = 3
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
        messages = [
            {"role": "system", "content": self._system_prompt(mode)},
            {"role": "user", "content": user_message.content},
        ]
        if tool_calls:
            messages.append({
                "role": "user",
                "content": "已执行的只读工具结果如下，请据此回答：\n" + json.dumps(
                    tool_calls, ensure_ascii=False, separators=(",", ":"),
                ),
            })
        try:
            assistant_content, model_tool_calls = await self._run_model_tool_loop(
                actor_id=str(actor_id), messages=messages,
            )
            tool_calls.extend(model_tool_calls)
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

    async def _run_model_tool_loop(self, *, actor_id: str, messages: list[dict]) -> tuple[str, list[dict]]:
        executed_calls: list[dict] = []
        for _turn in range(_MAX_MODEL_TOOL_TURNS):
            invocation = await self._platform.invoke_chat(
                provider_group="ai",
                model=None,
                payload={
                    "messages": messages,
                    "tools": self._tool_schemas(),
                    "tool_choice": "auto",
                    "temperature": 0,
                },
                quota_scope=("user", actor_id),
            )
            output = invocation.get("output") if isinstance(invocation, dict) else {}
            assistant_message = self._assistant_message(output)
            model_calls = self._model_tool_calls(output, assistant_message)
            if not model_calls:
                return str(assistant_message.get("content") or ""), executed_calls

            messages.append(assistant_message)
            for model_call in model_calls:
                executed = await self._execute_model_tool_call(actor_id, model_call)
                executed_calls.append(executed)
                messages.append({
                    "role": "tool",
                    "tool_call_id": str(model_call.get("id") or ""),
                    "content": json.dumps(executed["result"], ensure_ascii=False, separators=(",", ":")),
                })

        return "已达到工具调用上限，请基于已获取的信息继续提问。", executed_calls

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

    async def _execute_model_tool_call(self, actor_id: str, model_call: dict) -> dict:
        function = model_call.get("function") if isinstance(model_call, dict) else None
        name = str(function.get("name") or "") if isinstance(function, dict) else ""
        raw_arguments = function.get("arguments") if isinstance(function, dict) else None
        try:
            arguments = self._model_tool_arguments(raw_arguments)
            return (await self._execute_tools(actor_id, [{"name": name, "arguments": arguments}]))[0]
        except (NotFoundException, ValidationException, ValueError, json.JSONDecodeError) as exc:
            return {
                "name": name or "unknown_tool",
                "arguments": {},
                "result": {"error": str(exc) or "Tool request rejected"},
            }

    @staticmethod
    def _model_tool_arguments(raw_arguments) -> dict:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not isinstance(raw_arguments, str) or len(raw_arguments) > 16_384:
            raise ValidationException("Invalid AI tool arguments")
        arguments = json.loads(raw_arguments or "{}")
        if not isinstance(arguments, dict):
            raise ValidationException("Invalid AI tool arguments")
        return arguments

    @staticmethod
    def _assistant_message(output) -> dict:
        if isinstance(output, dict):
            message = output.get("message")
            if isinstance(message, dict):
                return {"role": "assistant", **message}
            return {"role": "assistant", "content": str(output.get("text") or "")}
        return {"role": "assistant", "content": str(output or "")}

    @staticmethod
    def _model_tool_calls(output, message: dict) -> list[dict]:
        calls = output.get("tool_calls") if isinstance(output, dict) else None
        calls = calls or message.get("tool_calls") or []
        return [call for call in calls if isinstance(call, dict)] if isinstance(calls, list) else []

    @staticmethod
    def _tool_schemas() -> list[dict]:
        def schema(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
            parameters = {"type": "object", "properties": properties, "additionalProperties": False}
            if required:
                parameters["required"] = required
            return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}

        return [
            schema("list_visible_sources", "List sources visible to the current user.", {}),
            schema("get_source_rule_summary", "Read the safe rule summary of one visible source version.", {
                "source_version_id": {"type": "string", "minLength": 1},
            }, ["source_version_id"]),
            schema("list_ai_analysis_results", "List the current user's prior AI analysis results.", {}),
        ]

    @staticmethod
    def _system_prompt(mode: str) -> str:
        return (
            MODE_PROMPTS[mode]
            + " You may use only the listed read-only tools when evidence is needed."
            + " Never request secrets, publish sources, write data, browse arbitrary URLs, or run code."
        )

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
