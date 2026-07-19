import json
from dataclasses import dataclass
from uuid import uuid4

from app.core.pagination import paginated_result
from app.core.redaction import sanitize_error, sanitize_for_boundary
from app.core.exceptions import AuthorizationException, NotFoundException, ValidationException
from app.domain.entities.ai_conversation import AIConversation, AIConversationMessage
from app.domain.entities.auth import AuditEvent


_SENSITIVE_KEY_PARTS = ("cookie", "token", "authorization", "provider", "internal", "api_key", "apikey")
_MAX_MODEL_TOOL_TURNS = 4
_CONTENT_RETRIEVAL_TOOL_NAMES = frozenset({"source.search", "toc.get", "chapter.fetch"})
_SOURCE_JOINT_TEST_TOOL_NAMES = frozenset({"source.joint_test"})
_CONTENT_ANALYSIS_TERMS = (
    "人物", "角色", "生平", "经历", "身世", "主角", "配角", "剧情", "情节",
    "世界观", "设定", "时间线", "结局", "故事内容", "发生了什么",
)
_DEFAULT_TOOL_NAMES = frozenset({
    "list_visible_sources", "get_source_rule_summary", "list_ai_analysis_results",
}) | _CONTENT_RETRIEVAL_TOOL_NAMES
_SOURCE_READ_TOOL_NAMES = frozenset({"get_source_validation_summary"})
_SOURCE_WRITE_TOOL_NAMES = frozenset({"create_source_rule_draft"})
_ALL_TOOL_NAMES = _DEFAULT_TOOL_NAMES | _SOURCE_READ_TOOL_NAMES | _SOURCE_WRITE_TOOL_NAMES | _SOURCE_JOINT_TEST_TOOL_NAMES
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


@dataclass(frozen=True)
class _ToolRequest:
    name: str
    arguments: dict

    @classmethod
    def parse(cls, value: object) -> "_ToolRequest":
        payload = _strict_mapping(value, required=("name",), optional=("arguments",))
        name = payload["name"]
        arguments = payload.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise ValidationException("Invalid AI tool request")
        return cls(name=name, arguments=arguments)


@dataclass(frozen=True)
class _ToolLoopResult:
    content: str
    tool_calls: list[dict]
    authorization_request: dict | None = None


@dataclass(frozen=True)
class _SourceVersionArguments:
    source_version_id: str

    @classmethod
    def parse(cls, value: object) -> "_SourceVersionArguments":
        payload = _strict_mapping(value, required=("source_version_id",))
        source_version_id = payload["source_version_id"]
        if not isinstance(source_version_id, str):
            raise ValidationException("Invalid source version arguments")
        return cls(source_version_id=source_version_id)


@dataclass(frozen=True)
class _SourceRuleDraftArguments:
    source_version_id: str
    patch: dict

    @classmethod
    def parse(cls, value: object) -> "_SourceRuleDraftArguments":
        payload = _strict_mapping(value, required=("source_version_id", "patch"))
        source_version_id = payload["source_version_id"]
        patch = payload["patch"]
        if not isinstance(source_version_id, str) or not isinstance(patch, dict):
            raise ValidationException("Invalid source rule draft arguments")
        return cls(source_version_id=source_version_id, patch=patch)


def _strict_mapping(value: object, *, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> dict:
    if not isinstance(value, dict):
        raise ValidationException("Invalid AI tool arguments")
    allowed = set(required) | set(optional)
    if set(value) - allowed or any(key not in value for key in required):
        raise ValidationException("Invalid AI tool arguments")
    return value


def _require_empty_arguments(value: object) -> None:
    if not isinstance(value, dict) or value:
        raise ValidationException("Invalid AI tool arguments")


class AIWorkspaceService:
    def __init__(
        self,
        platform,
        conversations,
        sources,
        ai_tasks,
        audit,
        source_runtime=None,
        novel_tool_executor=None,
        source_joint_test_executor=None,
        authorization_service=None,
    ):
        self._platform = platform
        self._conversations = conversations
        self._sources = sources
        self._ai_tasks = ai_tasks
        self._audit = audit
        self._source_runtime = source_runtime
        self._novel_tool_executor = novel_tool_executor
        self._source_joint_test_executor = source_joint_test_executor
        self._authorization_service = authorization_service

    async def create_conversation(self, actor_id: str, title: str = "") -> dict:
        conversation = self._conversations.create_conversation(
            AIConversation(id=uuid4().hex, actor_id=str(actor_id), title=title.strip() or "新对话")
        )
        await self._audit_event(actor_id, "ai.conversation.create", conversation.id)
        return self._serialize_conversation(conversation)

    async def list_conversations(self, actor_id: str) -> list[dict]:
        return [self._serialize_conversation(item) for item in self._conversations.list_conversations(str(actor_id))]

    async def list_conversations_page(
        self,
        actor_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
    ) -> dict:
        if hasattr(self._conversations, "list_conversations_page"):
            rows, total = self._conversations.list_conversations_page(
                str(actor_id),
                page=page,
                page_size=page_size,
                search=search,
            )
        else:
            all_rows = self._conversations.list_conversations(str(actor_id))
            normalized = search.strip().lower()
            filtered = [
                item for item in all_rows
                if not normalized or normalized in f"{item.id} {item.title}".lower()
            ]
            total = len(filtered)
            rows = filtered[(page - 1) * page_size : page * page_size]
        return paginated_result(
            [self._serialize_conversation(item) for item in rows],
            page=page,
            page_size=page_size,
            total=total,
            search=search,
        )

    def get_conversation(self, conversation_id: str, actor_id: str) -> dict:
        conversation = self._conversations.get_conversation(conversation_id, str(actor_id))
        if conversation is None:
            raise NotFoundException("AI conversation not found")
        return {
            **self._serialize_conversation(conversation),
            "messages": [self._serialize_message(item) for item in self._conversations.list_messages(conversation.id)],
            "authorization_requests": (
                self._authorization_service.list_pending(str(actor_id), conversation.id)
                if self._authorization_service is not None else []
            ),
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
        require_content_evidence = self._requires_content_evidence(mode, content)
        messages = [
            {"role": "system", "content": self._system_prompt(mode, tools, require_content_evidence)},
            {"role": "user", "content": user_message.content},
        ]
        authorized_content_tools = self._authorized_content_tools(actor_id, conversation.id, tools)
        tool_calls, authorization_request = await self._execute_explicit_tool_requests(
            actor_id=str(actor_id),
            conversation_id=conversation.id,
            message_id=user_message.id,
            mode=mode,
            messages=messages,
            tool_requests=tool_requests or [],
            allowed_tool_names=tools,
            authorized_content_tools=authorized_content_tools,
            require_content_evidence=require_content_evidence,
        )
        if tool_calls:
            messages.append({
                "role": "user",
                "content": "已执行的只读工具结果如下，请据此回答：\n" + json.dumps(
                    tool_calls, ensure_ascii=False, separators=(",", ":"),
                ),
            })
        if authorization_request is not None:
            assistant = self._append_authorization_message(
                conversation.id,
                mode,
                tool_calls,
                authorization_request,
            )
            await self._audit_event(actor_id, "ai.conversation.message", conversation.id)
            return self._serialize_message(assistant)
        try:
            loop_result = await self._run_model_tool_loop(
                actor_id=str(actor_id),
                conversation_id=conversation.id,
                message_id=user_message.id,
                mode=mode,
                messages=messages,
                allowed_tool_names=tools,
                require_content_evidence=require_content_evidence,
                authorized_content_tools=authorized_content_tools,
            )
            tool_calls.extend(loop_result.tool_calls)
            if loop_result.authorization_request is not None:
                assistant = self._append_authorization_message(
                    conversation.id,
                    mode,
                    tool_calls,
                    loop_result.authorization_request,
                )
                await self._audit_event(actor_id, "ai.conversation.message", conversation.id)
                return self._serialize_message(assistant)
            assistant = self._conversations.append_message(
                AIConversationMessage(
                    id=uuid4().hex,
                    conversation_id=conversation.id,
                    role="assistant",
                    mode=mode,
                    content=loop_result.content,
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
                    content=sanitize_error(exc),
                    status="failed",
                    tool_calls=tool_calls,
                )
            )
        await self._audit_event(actor_id, "ai.conversation.message", conversation.id)
        return self._serialize_message(assistant)

    async def decide_authorization(
        self,
        request_id: str,
        *,
        actor_id: str,
        conversation_id: str,
        decision: str,
        rbac_permissions: set[str] | None = None,
    ) -> dict:
        if self._authorization_service is None:
            raise ValidationException("AI conversation authorization is unavailable")
        if rbac_permissions is not None and "book_sources.read" not in rbac_permissions:
            raise AuthorizationException("Permission denied: book_sources.read")
        original_request = self._authorization_service.get_request_record(
            request_id,
            actor_id=str(actor_id),
            conversation_id=str(conversation_id),
        )
        original_mode = str(original_request.continuation.get("mode") or "chat") if original_request is not None else "chat"
        authorization = await self._authorization_service.decide(
            request_id,
            actor_id=str(actor_id),
            conversation_id=str(conversation_id),
            decision=decision,
        )
        if authorization.get("status") == "denied":
            existing = self._authorization_message_for_request(conversation_id, request_id)
            if existing is not None:
                return {"authorization": authorization, "message": self._serialize_message(existing)}
            message = self._append_assistant_message(
                conversation_id,
                original_mode,
                "你拒绝了正文读取授权，本轮不会基于模型记忆生成原文结论。",
                [],
                status="denied",
                metadata={"authorization": authorization},
            )
            return {"authorization": authorization, "message": self._serialize_message(message)}
        if authorization.get("status") != "processing":
            message_id = authorization.get("result_message_id")
            if message_id:
                for message in self._conversations.list_messages(conversation_id):
                    if message.id == message_id:
                        return {"authorization": authorization, "message": self._serialize_message(message)}
            return {"authorization": authorization}
        request = self._authorization_service.get_request_record(
            request_id,
            actor_id=str(actor_id),
            conversation_id=str(conversation_id),
        )
        if request is None:
            raise NotFoundException("AI authorization request not found")
        continuation = request.continuation
        messages = continuation.get("messages") if isinstance(continuation, dict) else []
        pending_call = continuation.get("pending_call") if isinstance(continuation, dict) else None
        pending_calls = continuation.get("pending_calls") if isinstance(continuation, dict) else None
        executed_calls = continuation.get("executed_calls") if isinstance(continuation, dict) else []
        if not isinstance(pending_calls, list) or not pending_calls:
            pending_calls = [pending_call]
        if not isinstance(messages, list) or not all(isinstance(call, dict) for call in pending_calls):
            await self._authorization_service.finalize(request_id, actor_id=str(actor_id), status="failed")
            raise ValidationException("AI authorization continuation is invalid")
        allowed_names = frozenset(continuation.get("allowed_tool_names") or _DEFAULT_TOOL_NAMES)
        authorized_content_tools = set(_CONTENT_RETRIEVAL_TOOL_NAMES)
        executed_calls = list(executed_calls) if isinstance(executed_calls, list) else []
        messages = list(messages)
        last_executed: dict | None = None
        for pending_call in pending_calls:
            executed = await self._execute_model_tool_call(str(actor_id), pending_call, allowed_names)
            executed_calls.append(executed)
            last_executed = executed
            messages.append({
                "role": "tool",
                "tool_call_id": str(pending_call.get("id") or ""),
                "content": json.dumps(executed["result"], ensure_ascii=False, separators=(",", ":")),
            })
            if self._is_rejected_tool_result(executed.get("result")):
                break
        if last_executed is not None and self._is_rejected_tool_result(last_executed.get("result")):
            content = "书源读取工具未能取得证据，已停止重复尝试。请先启用并发布健康书源后重试。"
            assistant = self._append_assistant_message(conversation_id, continuation.get("mode", "chat"), content, executed_calls)
            finalized = await self._authorization_service.finalize(request_id, actor_id=str(actor_id), status="failed", result_message_id=assistant.id)
            return {"authorization": finalized, "message": self._serialize_message(assistant)}
        loop_result = await self._run_model_tool_loop(
            actor_id=str(actor_id),
            conversation_id=str(conversation_id),
            message_id=request.message_id,
            mode=str(continuation.get("mode") or "chat"),
            messages=messages,
            allowed_tool_names=allowed_names,
            require_content_evidence=bool(continuation.get("require_content_evidence")),
            authorized_content_tools=authorized_content_tools,
            executed_calls=executed_calls,
        )
        if loop_result.authorization_request is not None:
            assistant = self._append_authorization_message(conversation_id, continuation.get("mode", "chat"), loop_result.tool_calls, loop_result.authorization_request)
            await self._authorization_service.finalize(request_id, actor_id=str(actor_id), status="failed", result_message_id=assistant.id)
            return {"authorization": loop_result.authorization_request, "message": self._serialize_message(assistant)}
        assistant = self._append_assistant_message(
            conversation_id,
            str(continuation.get("mode") or "chat"),
            loop_result.content,
            loop_result.tool_calls,
        )
        finalized = await self._authorization_service.finalize(
            request_id,
            actor_id=str(actor_id),
            status="consumed",
            result_message_id=assistant.id,
        )
        return {"authorization": finalized, "message": self._serialize_message(assistant)}

    def list_pending_authorizations(self, actor_id: str, conversation_id: str) -> list[dict]:
        if self._authorization_service is None:
            return []
        return self._authorization_service.list_pending(str(actor_id), str(conversation_id))

    def list_authorization_grants(self, actor_id: str, conversation_id: str | None = None) -> list[dict]:
        if self._authorization_service is None:
            return []
        return self._authorization_service.list_grants(str(actor_id), conversation_id)

    async def revoke_authorization_grant(self, grant_id: str, *, actor_id: str) -> dict:
        if self._authorization_service is None:
            raise ValidationException("AI conversation authorization is unavailable")
        return await self._authorization_service.revoke_grant(grant_id, actor_id=str(actor_id))

    async def _run_model_tool_loop(
        self,
        *,
        actor_id: str,
        conversation_id: str,
        message_id: str,
        mode: str,
        messages: list[dict],
        allowed_tool_names: frozenset[str],
        require_content_evidence: bool = False,
        authorized_content_tools: set[str] | frozenset[str] | None = None,
        executed_calls: list[dict] | None = None,
    ) -> _ToolLoopResult:
        if require_content_evidence and not (_CONTENT_RETRIEVAL_TOOL_NAMES & allowed_tool_names):
            return _ToolLoopResult("未获授权读取书籍原文，不能基于模型记忆生成人物、剧情或世界观结论。", [])
        executed_calls = list(executed_calls or [])
        authorized_content_tools = set(authorized_content_tools or set())
        seen_tool_calls: set[str] = set()
        for call in executed_calls:
            if isinstance(call, dict):
                seen_tool_calls.add(json.dumps({"name": call.get("name"), "arguments": call.get("arguments")}, ensure_ascii=False, sort_keys=True, default=str))
        for _turn in range(_MAX_MODEL_TOOL_TURNS):
            has_chapter_evidence = self._has_chapter_evidence(executed_calls)
            model_tool_names = allowed_tool_names
            if require_content_evidence and not has_chapter_evidence:
                model_tool_names = frozenset(_CONTENT_RETRIEVAL_TOOL_NAMES & allowed_tool_names)
                if not executed_calls:
                    model_tool_names = frozenset({"source.search"})
            invocation = await self._platform.invoke_chat(
                provider_group="ai",
                model=None,
                payload={
                    "messages": messages,
                    "tools": self._tool_schemas(model_tool_names),
                    "tool_choice": "required" if require_content_evidence and not has_chapter_evidence else "auto",
                    "temperature": 0,
                },
                quota_scope=("user", actor_id),
            )
            output = invocation.get("output") if isinstance(invocation, dict) else {}
            assistant_message = self._assistant_message(output)
            model_calls = self._model_tool_calls(output, assistant_message)
            if not model_calls:
                if require_content_evidence and not self._has_chapter_evidence(executed_calls):
                    return _ToolLoopResult("未能取得可验证的书籍正文证据，不能基于模型记忆生成人物、剧情或世界观结论。", executed_calls)
                return _ToolLoopResult(str(assistant_message.get("content") or ""), executed_calls)

            messages.append(assistant_message)
            for model_call in model_calls:
                fingerprint = self._model_tool_call_fingerprint(model_call)
                if fingerprint in seen_tool_calls:
                    return _ToolLoopResult("检测到模型重复调用同一书源工具，已停止循环。请提供更具体的书名、章节或检查书源规则。", executed_calls)
                seen_tool_calls.add(fingerprint)
                function = model_call.get("function") if isinstance(model_call, dict) else None
                name = str(function.get("name") or "") if isinstance(function, dict) else ""
                if self._authorization_service is not None and name in _CONTENT_RETRIEVAL_TOOL_NAMES and name not in authorized_content_tools:
                    arguments = self._model_tool_arguments(function.get("arguments") if isinstance(function, dict) else None)
                    authorization_request = await self._create_authorization_request(
                        actor_id=actor_id,
                        conversation_id=conversation_id,
                        message_id=message_id,
                        mode=mode,
                        messages=messages,
                        executed_calls=executed_calls,
                        pending_call=model_call,
                        allowed_tool_names=allowed_tool_names,
                        require_content_evidence=require_content_evidence,
                        requested_tools=[name],
                        requested_calls=[{"name": name, "arguments": arguments}],
                    )
                    return _ToolLoopResult("需要你的授权才能读取书源原文。", executed_calls, authorization_request)
                executed = await self._execute_model_tool_call(actor_id, model_call, allowed_tool_names)
                executed_calls.append(executed)
                if self._is_rejected_tool_result(executed.get("result")):
                    return _ToolLoopResult("书源读取工具未能取得证据，已停止重复尝试。请先启用并发布健康书源后重试。", executed_calls)
                messages.append({
                    "role": "tool",
                    "tool_call_id": str(model_call.get("id") or ""),
                    "content": json.dumps(executed["result"], ensure_ascii=False, separators=(",", ":")),
                })

        return _ToolLoopResult("已达到工具调用上限，请基于已获取的信息继续提问。", executed_calls)

    def _authorized_content_tools(self, actor_id: str, conversation_id: str, allowed_tool_names: frozenset[str]) -> set[str]:
        available = set(_CONTENT_RETRIEVAL_TOOL_NAMES & allowed_tool_names)
        if self._authorization_service is None:
            return available
        permissions = {"book_sources.read"} if available else set()
        return set(self._authorization_service.active_tool_names(actor_id, conversation_id, permissions)) & available

    async def _execute_explicit_tool_requests(
        self,
        *,
        actor_id: str,
        conversation_id: str,
        message_id: str,
        mode: str,
        messages: list[dict],
        tool_requests: list[dict],
        allowed_tool_names: frozenset[str],
        authorized_content_tools: set[str],
        require_content_evidence: bool,
    ) -> tuple[list[dict], dict | None]:
        if not tool_requests:
            return [], None
        safe_requests: list[dict] = []
        pending: list[_ToolRequest] = []
        for raw_request in tool_requests:
            request = _ToolRequest.parse(raw_request)
            if request.name not in _ALL_TOOL_NAMES:
                raise ValidationException("Unsupported AI tool")
            if request.name not in allowed_tool_names:
                raise ValidationException("AI tool is not granted for this request")
            if (
                self._authorization_service is not None
                and request.name in _CONTENT_RETRIEVAL_TOOL_NAMES
                and request.name not in authorized_content_tools
            ):
                pending.append(request)
            else:
                safe_requests.append(raw_request)
        executed = await self._execute_tools(actor_id, safe_requests, allowed_tool_names)
        if not pending:
            return executed, None
        pending_calls = [
            {
                "id": uuid4().hex,
                "type": "function",
                "function": {
                    "name": item.name,
                    "arguments": json.dumps(item.arguments, ensure_ascii=False),
                },
            }
            for item in pending
        ]
        continuation_messages = list(messages)
        if executed:
            continuation_messages.append({
                "role": "user",
                "content": "已执行的只读工具结果如下，请据此回答：\n" + json.dumps(executed, ensure_ascii=False, separators=(",", ":")),
            })
        authorization = await self._create_authorization_request(
            actor_id=actor_id,
            conversation_id=conversation_id,
            message_id=message_id,
            mode=mode,
            messages=continuation_messages,
            executed_calls=executed,
            pending_call=pending_calls[0],
            pending_calls=pending_calls,
            allowed_tool_names=allowed_tool_names,
            require_content_evidence=require_content_evidence,
            requested_tools=[item.name for item in pending],
            requested_calls=[{"name": item.name, "arguments": item.arguments} for item in pending],
        )
        return executed, authorization

    async def _create_authorization_request(
        self,
        *,
        actor_id: str,
        conversation_id: str,
        message_id: str,
        mode: str,
        messages: list[dict],
        executed_calls: list[dict],
        pending_call: dict,
        pending_calls: list[dict] | None = None,
        allowed_tool_names: frozenset[str],
        require_content_evidence: bool,
        requested_tools: list[str] | None = None,
        requested_calls: list[dict] | None = None,
    ) -> dict:
        continuation = {
            "messages": messages,
            "executed_calls": executed_calls,
            "pending_call": pending_call,
            "pending_calls": pending_calls or [pending_call],
            "mode": mode,
            "allowed_tool_names": sorted(allowed_tool_names),
            "require_content_evidence": require_content_evidence,
        }
        return await self._authorization_service.create_request(
            actor_id=actor_id,
            conversation_id=conversation_id,
            message_id=message_id,
            mode=mode,
            requested_tools=requested_tools or [str(pending_call.get("function", {}).get("name") or "")],
            requested_calls=requested_calls or [{"name": str(pending_call.get("function", {}).get("name") or ""), "arguments": {}}],
            continuation=continuation,
        )

    def _append_authorization_message(self, conversation_id: str, mode: str, tool_calls: list[dict], authorization_request: dict) -> AIConversationMessage:
        return self._conversations.append_message(
            AIConversationMessage(
                id=uuid4().hex,
                conversation_id=conversation_id,
                role="assistant",
                mode=mode,
                content="需要你的授权才能读取书源原文。",
                status="authorization_required",
                tool_calls=tool_calls,
                metadata={"authorization_request": authorization_request},
            )
        )

    def _append_assistant_message(
        self,
        conversation_id: str,
        mode: str,
        content: str,
        tool_calls: list[dict],
        *,
        status: str = "succeeded",
        metadata: dict | None = None,
    ) -> AIConversationMessage:
        return self._conversations.append_message(
            AIConversationMessage(
                id=uuid4().hex,
                conversation_id=conversation_id,
                role="assistant",
                mode=mode if mode in MODE_PROMPTS else "chat",
                content=content,
                status=status,
                tool_calls=tool_calls,
                metadata=metadata or {},
            )
        )

    def _authorization_message_for_request(self, conversation_id: str, request_id: str) -> AIConversationMessage | None:
        for message in self._conversations.list_messages(conversation_id):
            metadata = message.metadata if isinstance(message.metadata, dict) else {}
            request = metadata.get("authorization")
            if isinstance(request, dict) and request.get("id") == request_id:
                return message
        return None

    async def _execute_tools(
        self,
        actor_id: str,
        tool_requests: list[dict],
        allowed_tool_names: frozenset[str],
    ) -> list[dict]:
        calls: list[dict] = []
        for raw_request in tool_requests:
            request = _ToolRequest.parse(raw_request)
            if request.name not in _ALL_TOOL_NAMES:
                raise ValidationException("Unsupported AI tool")
            if request.name not in allowed_tool_names:
                raise ValidationException("AI tool is not granted for this request")
            if request.name == "list_visible_sources":
                _require_empty_arguments(request.arguments)
                result = self._list_visible_sources(str(actor_id))
            elif request.name == "get_source_rule_summary":
                args = _SourceVersionArguments.parse(request.arguments)
                result = self._get_source_rule_summary(args.source_version_id, str(actor_id))
            elif request.name == "list_ai_analysis_results":
                _require_empty_arguments(request.arguments)
                result = self._list_ai_results(str(actor_id))
            elif request.name == "get_source_validation_summary":
                args = _SourceVersionArguments.parse(request.arguments)
                result = self._get_source_validation_summary(args.source_version_id, str(actor_id))
            elif request.name == "create_source_rule_draft":
                args = _SourceRuleDraftArguments.parse(request.arguments)
                result = await self._create_source_rule_draft(args.source_version_id, args.patch, str(actor_id))
            elif request.name == "source.joint_test":
                if self._source_joint_test_executor is None:
                    raise ValidationException("Source joint testing is unavailable")
                tool_result = await self._source_joint_test_executor.ainvoke(
                    {**request.arguments, "tenant_id": str(actor_id)},
                )
                result = (
                    tool_result.data
                    if tool_result.status == "accepted"
                    else {"status": tool_result.status, "error": tool_result.error_code or "tool_rejected"}
                )
            elif request.name in _CONTENT_RETRIEVAL_TOOL_NAMES:
                if self._novel_tool_executor is None:
                    raise ValidationException("Novel content retrieval is unavailable")
                tool_result = await self._novel_tool_executor.ainvoke(
                    request.name,
                    {**request.arguments, "tenant_id": str(actor_id)},
                )
                result = (
                    tool_result.data
                    if tool_result.status == "accepted"
                    else {"status": tool_result.status, "error": tool_result.error_code or "tool_rejected"}
                )
            else:
                raise ValidationException("Unsupported AI tool")
            sanitized = _sanitize(result)
            calls.append({
                "name": request.name,
                "arguments": _sanitize(request.arguments),
                "result": sanitized,
            })
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
                "result": {"error": sanitize_error(exc) or "Tool request rejected"},
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

    @classmethod
    def _model_tool_call_fingerprint(cls, model_call: dict) -> str:
        function = model_call.get("function") if isinstance(model_call, dict) else None
        if not isinstance(function, dict):
            return json.dumps({"name": "", "arguments": None}, sort_keys=True)
        name = str(function.get("name") or "")
        raw_arguments = function.get("arguments")
        try:
            arguments = cls._model_tool_arguments(raw_arguments)
        except (ValidationException, ValueError, json.JSONDecodeError):
            arguments = raw_arguments
        return json.dumps(
            {"name": name, "arguments": arguments},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    @staticmethod
    def _is_rejected_tool_result(result: object) -> bool:
        return isinstance(result, dict) and result.get("status") == "rejected"

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
    def _has_chapter_evidence(tool_calls: list[dict]) -> bool:
        for call in tool_calls:
            if call.get("name") != "chapter.fetch":
                continue
            result = call.get("result")
            if isinstance(result, dict) and result.get("evidence_span_ids"):
                return True
        return False

    @staticmethod
    def _requires_content_evidence(mode: str, content: str) -> bool:
        if mode in {"character", "storyline", "world"}:
            return True
        return mode == "chat" and any(term in content for term in _CONTENT_ANALYSIS_TERMS)

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
            schema("source.joint_test", "Run the candidate-only source build, search, TOC, content, complement, and insight acceptance chain with real evidence.", {
                "source_urls": {"type": "array", "items": {"type": "string", "format": "uri"}, "minItems": 1, "maxItems": 4},
                "book_name": {"type": "string", "minLength": 1, "maxLength": 300},
                "author_hint": {"type": "string", "maxLength": 200},
                "chapter_index": {"type": "integer", "minimum": 0, "maximum": 100000},
                "chapter_title": {"type": "string", "maxLength": 300},
                "use_ai": {"type": "boolean"},
            }, ["source_urls", "book_name"]),
            schema("source.search", "Search the user's enabled book sources for a work before analysis.", {
                "keyword": {"type": "string", "minLength": 1, "maxLength": 200},
                "source_ids": {"type": "array", "items": {"type": "integer"}, "maxItems": 20},
                "author_hint": {"type": "string", "maxLength": 200},
            }, ["keyword"]),
            schema("toc.get", "Read a book's table of contents to select relevant chapters.", {
                "source_id": {"type": "integer"},
                "book_url": {"type": "string", "minLength": 1, "maxLength": 2048},
                "book_name": {"type": "string", "minLength": 1, "maxLength": 300},
                "author_hint": {"type": "string", "maxLength": 200},
            }, ["source_id", "book_url", "book_name"]),
            schema("chapter.fetch", "Fetch and store one relevant chapter as verifiable evidence before making a literary claim.", {
                "source_id": {"type": "integer"},
                "book_url": {"type": "string", "minLength": 1, "maxLength": 2048},
                "book_name": {"type": "string", "minLength": 1, "maxLength": 300},
                "chapter_index": {"type": "integer", "minimum": 0, "maximum": 100000},
                "author_hint": {"type": "string", "maxLength": 200},
            }, ["source_id", "book_url", "book_name", "chapter_index"]),
        ]
        return [item for item in schemas if item["function"]["name"] in allowed_tool_names]

    @staticmethod
    def _system_prompt(mode: str, allowed_tool_names: frozenset[str], require_content_evidence: bool = False) -> str:
        candidate_draft_allowed = bool(_SOURCE_WRITE_TOOL_NAMES & allowed_tool_names)
        return (
            MODE_PROMPTS[mode]
            + " You may use only the listed tools when evidence is needed."
            + (
                " For character, storyline, and world analysis, you must retrieve source.search, toc.get, and chapter.fetch evidence before answering. "
                "Never use parametric knowledge; if chapter evidence is unavailable, state that no conclusion can be made."
                if require_content_evidence else ""
            )
            + (" Candidate rule drafts may be created but never published." if candidate_draft_allowed else "")
            + (
                " For source validation, you must call source.joint_test and base conclusions only on its returned search, TOC, content, complement, and insight evidence. Never use parametric knowledge or publish a source."
                if "source.joint_test" in allowed_tool_names else ""
            )
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
            if row.status == "published" or (row.status == "candidate" and str(row.created_by) == actor_id)
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
        payload = {
            "id": item.id,
            "role": item.role,
            "mode": item.mode,
            "content": item.content,
            "status": item.status,
            "tool_calls": item.tool_calls,
            "metadata": item.metadata,
            "created_at": item.created_at.isoformat(),
        }
        if isinstance(item.metadata, dict) and item.metadata.get("authorization_request") is not None:
            payload["authorization_request"] = item.metadata["authorization_request"]
        return payload


def _sanitize(value):
    return sanitize_for_boundary(value)
