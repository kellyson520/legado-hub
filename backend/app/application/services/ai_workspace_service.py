import json
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.application.services.ai_service import AIService
from app.core.exceptions import NotFoundException, ValidationException
from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage
from app.domain.entities.auth import AuditEvent


_SENSITIVE_KEY_PARTS = ("cookie", "token", "authorization", "provider", "internal", "api_key", "apikey")
_MAX_MODEL_TOOL_TURNS = 3
_DEFAULT_TOOL_NAMES = frozenset({
    "list_visible_sources", "get_source_rule_summary", "list_ai_analysis_results",
})
_SOURCE_READ_TOOL_NAMES = frozenset({"get_source_validation_summary"})
_SOURCE_WRITE_TOOL_NAMES = frozenset({"create_source_rule_draft"})
_ALL_TOOL_NAMES = _DEFAULT_TOOL_NAMES | _SOURCE_READ_TOOL_NAMES | _SOURCE_WRITE_TOOL_NAMES
_ALLOWED_DRAFT_PATCH_FIELDS = frozenset({
    "bookSourceName", "bookSourceUrl", "bookSourceGroup", "enabled", "searchUrl",
    "ruleSearch", "ruleBookInfo", "ruleToc", "ruleContent", "bookSourceComment",
})
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


class _SourceRuleDraftArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_version_id: str
    patch: dict


class AIWorkspaceService:
    def __init__(self, platform, conversations, sources, ai_tasks, audit, source_runtime=None):
        self._platform = platform
        self._conversations = conversations
        self._sources = sources
        self._ai_tasks = ai_tasks
        self._audit = audit
        self._source_runtime = source_runtime

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
        allowed_tool_names: set[str] | frozenset[str] | None = None,
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
        tools = _DEFAULT_TOOL_NAMES if allowed_tool_names is None else frozenset(allowed_tool_names)
        tool_calls = await self._execute_tools(actor_id, tool_requests or [], tools)
        messages = [
            {"role": "system", "content": self._system_prompt(mode, tools)},
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
                actor_id=str(actor_id), messages=messages, allowed_tool_names=tools,
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

    async def _run_model_tool_loop(
        self,
        *,
        actor_id: str,
        messages: list[dict],
        allowed_tool_names: frozenset[str],
    ) -> tuple[str, list[dict]]:
        executed_calls: list[dict] = []
        for _turn in range(_MAX_MODEL_TOOL_TURNS):
            invocation = await self._platform.invoke_chat(
                provider_group="ai",
                model=None,
                payload={
                    "messages": messages,
                    "tools": self._tool_schemas(allowed_tool_names),
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
                executed = await self._execute_model_tool_call(actor_id, model_call, allowed_tool_names)
                executed_calls.append(executed)
                messages.append({
                    "role": "tool",
                    "tool_call_id": str(model_call.get("id") or ""),
                    "content": json.dumps(executed["result"], ensure_ascii=False, separators=(",", ":")),
                })

        return "已达到工具调用上限，请基于已获取的信息继续提问。", executed_calls

    async def _execute_tools(
        self,
        actor_id: str,
        tool_requests: list[dict],
        allowed_tool_names: frozenset[str],
    ) -> list[dict]:
        calls: list[dict] = []
        for raw_request in tool_requests:
            request = _ToolRequest.model_validate(raw_request)
            if request.name not in _ALL_TOOL_NAMES:
                raise ValidationException("Unsupported AI tool")
            if request.name not in allowed_tool_names:
                raise ValidationException("AI tool is not granted for this request")
            if request.name == "list_visible_sources":
                _EmptyArguments.model_validate(request.arguments)
                result = self._list_visible_sources(str(actor_id))
            elif request.name == "get_source_rule_summary":
                args = _SourceVersionArguments.model_validate(request.arguments)
                result = self._get_source_rule_summary(args.source_version_id, str(actor_id))
            elif request.name == "list_ai_analysis_results":
                _EmptyArguments.model_validate(request.arguments)
                result = self._list_ai_results(str(actor_id))
            elif request.name == "get_source_validation_summary":
                args = _SourceVersionArguments.model_validate(request.arguments)
                result = self._get_source_validation_summary(args.source_version_id, str(actor_id))
            elif request.name == "create_source_rule_draft":
                args = _SourceRuleDraftArguments.model_validate(request.arguments)
                result = await self._create_source_rule_draft(args.source_version_id, args.patch, str(actor_id))
            else:
                raise ValidationException("Unsupported AI tool")
            sanitized = _sanitize(result)
            calls.append({"name": request.name, "arguments": request.arguments, "result": sanitized})
            await self._audit_event(actor_id, "ai.tool.invoke", request.name)
        return calls

    async def _execute_model_tool_call(
        self,
        actor_id: str,
        model_call: dict,
        allowed_tool_names: frozenset[str],
    ) -> dict:
        function = model_call.get("function") if isinstance(model_call, dict) else None
        name = str(function.get("name") or "") if isinstance(function, dict) else ""
        raw_arguments = function.get("arguments") if isinstance(function, dict) else None
        try:
            arguments = self._model_tool_arguments(raw_arguments)
            return (await self._execute_tools(
                actor_id,
                [{"name": name, "arguments": arguments}],
                allowed_tool_names,
            ))[0]
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
    def _tool_schemas(allowed_tool_names: frozenset[str] = _DEFAULT_TOOL_NAMES) -> list[dict]:
        def schema(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
            parameters = {"type": "object", "properties": properties, "additionalProperties": False}
            if required:
                parameters["required"] = required
            return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}

        schemas = [
            schema("list_visible_sources", "List sources visible to the current user.", {}),
            schema("get_source_rule_summary", "Read the safe rule summary of one visible source version.", {
                "source_version_id": {"type": "string", "minLength": 1},
            }, ["source_version_id"]),
            schema("list_ai_analysis_results", "List the current user's prior AI analysis results.", {}),
            schema("get_source_validation_summary", "Read the latest validation evidence for one visible source version.", {
                "source_version_id": {"type": "string", "minLength": 1},
            }, ["source_version_id"]),
            schema("create_source_rule_draft", "Create a candidate-only rule revision for one visible source. It never publishes.", {
                "source_version_id": {"type": "string", "minLength": 1},
                "patch": {"type": "object", "minProperties": 1},
            }, ["source_version_id", "patch"]),
        ]
        return [item for item in schemas if item["function"]["name"] in allowed_tool_names]

    @staticmethod
    def _system_prompt(mode: str, allowed_tool_names: frozenset[str]) -> str:
        candidate_draft_allowed = bool(_SOURCE_WRITE_TOOL_NAMES & allowed_tool_names)
        return (
            MODE_PROMPTS[mode]
            + " You may use only the listed tools when evidence is needed."
            + (" Candidate rule drafts may be created but never published." if candidate_draft_allowed else "")
            + " Never request secrets, publish sources, browse arbitrary URLs, or run code."
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

    def _get_source_validation_summary(self, source_version_id: str, actor_id: str) -> dict:
        version = self._sources.get_version(source_version_id)
        if version is None or (version.status != "published" and str(version.created_by) != actor_id):
            raise NotFoundException("Source version not found")
        runs = self._sources.list_test_runs(source_version_id)
        latest = runs[0] if runs else None
        return {
            "source_version_id": version.id,
            "status": version.status,
            "latest_validation": None if latest is None else {
                "id": latest.id,
                "trigger": latest.trigger,
                "score": latest.score,
                "grade": latest.grade,
                "step_results": latest.step_results,
                "diagnostics": latest.diagnostics,
                "created_at": latest.created_at.isoformat() if latest.created_at else None,
            },
        }

    async def _create_source_rule_draft(self, source_version_id: str, patch: dict, actor_id: str) -> dict:
        version = self._sources.get_version(source_version_id)
        if version is None or (version.status != "published" and str(version.created_by) != actor_id):
            raise NotFoundException("Source version not found")
        if self._source_runtime is None:
            raise ValidationException("Source rule drafting is unavailable")
        if not patch or set(patch) - _ALLOWED_DRAFT_PATCH_FIELDS:
            raise ValidationException("Source rule patch contains unsupported fields")
        for field in ("ruleSearch", "ruleBookInfo", "ruleToc", "ruleContent"):
            if field in patch and (not isinstance(patch[field], dict) or not patch[field]):
                raise ValidationException(f"{field} must be a non-empty object")
        return await self._source_runtime.create_rule_draft(source_version_id, patch, actor_id)

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
