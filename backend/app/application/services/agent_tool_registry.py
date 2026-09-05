import inspect
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from app.core.exceptions import AuthorizationException
from app.domain.entities.agent_runtime import AgentTool, ToolResult


class AgentToolRegistry:
    """An in-process allowlist for bounded agent tool calls."""

    _TENANT_ARGUMENT_KEYS = frozenset({
        'tenant_id', 'tenantId', 'tenantID', 'tenant', 'tenant_ids', 'tenantIds',
    })

    def __init__(
        self,
        source_build_handlers: Mapping[str, Any] | None = None,
        novel_analysis_handlers: Mapping[str, Any] | None = None,
    ):
        tools = self._builtin_tools()
        allowed_handlers = frozenset({
            'source.inspect', 'source.probe', 'page.inspect', 'page.request',
            'rule.propose', 'rule.validate', 'review.request', 'source.joint_test',
        })
        for name, handler in (source_build_handlers or {}).items():
            if name not in allowed_handlers or name not in tools or not callable(handler):
                continue
            tool = tools[name]
            tools[name] = AgentTool(tool.name, tool.category, tool.allowed_agent_kinds, handler)
        allowed_novel_handlers = frozenset({
            'source.search', 'book.resolve', 'toc.get', 'chapter.fetch',
            'evidence.search', 'evidence.get',
            'novel.search_memory', 'novel.get_entity_profile', 'novel.get_mentions',
            'novel.get_relations', 'novel.timeline', 'novel.get_item_state',
            'novel.compare_entities', 'novel.get_chapter_evidence', 'novel.index_status',
        })
        for name, handler in (novel_analysis_handlers or {}).items():
            if name not in allowed_novel_handlers or name not in tools or not callable(handler):
                continue
            tool = tools[name]
            tools[name] = AgentTool(tool.name, tool.category, tool.allowed_agent_kinds, handler)
        self._tools: Mapping[str, AgentTool] = MappingProxyType(tools)

    def invoke(
        self,
        *,
        agent_kind: str,
        tool_name: str,
        arguments: dict[str, Any],
        tenant_id: str | None = None,
    ) -> ToolResult:
        tool = self._authorize(agent_kind, tool_name, arguments, tenant_id)
        if tool.handler is None:
            return ToolResult(status='rejected', error_code='tool_not_implemented')
        if self._is_async_handler(tool.handler):
            return ToolResult(status='rejected', error_code='async_tool_requires_ainvoke')
        result = tool.handler(self._handler_arguments(tool_name, arguments, tenant_id))
        if inspect.isawaitable(result):
            close = getattr(result, 'close', None)
            if callable(close):
                close()
            return ToolResult(status='rejected', error_code='async_tool_requires_ainvoke')
        return result

    async def ainvoke(
        self,
        *,
        agent_kind: str,
        tool_name: str,
        arguments: dict[str, Any],
        tenant_id: str | None = None,
    ) -> ToolResult:
        tool = self._authorize(agent_kind, tool_name, arguments, tenant_id)
        if tool.handler is None:
            return ToolResult(status='rejected', error_code='tool_not_implemented')
        result = tool.handler(self._handler_arguments(tool_name, arguments, tenant_id))
        return await result if inspect.isawaitable(result) else result

    def get(self, tool_name: str) -> AgentTool | None:
        return self._tools.get(tool_name)

    def list_tools(self) -> tuple[AgentTool, ...]:
        return tuple(self._tools.values())

    def _builtin_tools(self) -> dict[str, AgentTool]:
        tools: dict[str, AgentTool] = {}
        read_tools = (
            'work.search', 'work.get', 'chapter.get',
            'character.find', 'character.relations',
            'plot.find', 'plot.timeline', 'plot.thread',
            'world.find', 'world.relations', 'world.rules',
        )
        for name in read_tools:
            tools[name] = AgentTool(name, 'read', frozenset({'knowledge', 'source_build'}))

        novel_read_tools = (
            'chapter.search', 'character.profile', 'character.count',
            'character.aliases', 'character.relations', 'plot.timeline',
            'plot.state_changes', 'world.query', 'semantic.search',
            'evidence.get', 'chapter.summary', 'book.stats', 'reading.progress',
            'novel.search_memory', 'novel.get_entity_profile', 'novel.get_mentions',
            'novel.get_relations', 'novel.timeline', 'novel.get_item_state',
            'novel.compare_entities', 'novel.get_chapter_evidence', 'novel.index_status',
        )
        for name in novel_read_tools:
            tools[name] = AgentTool(name, 'read', frozenset({'novel', 'knowledge'}))

        tools.update({
            'novel.import_preview': AgentTool('novel.import_preview', 'read', frozenset({'novel', 'knowledge'})),
            'novel.chapter_quality': AgentTool('novel.chapter_quality', 'read', frozenset({'novel', 'knowledge'})),
            'source.build_status': AgentTool('source.build_status', 'read', frozenset({'source_build'})),
            'source.validation_report': AgentTool('source.validation_report', 'read', frozenset({'source_build'})),
            'source.search': AgentTool('source.search', 'read', frozenset({'knowledge'})),
            'book.resolve': AgentTool('book.resolve', 'read', frozenset({'knowledge'})),
            'toc.get': AgentTool('toc.get', 'read', frozenset({'knowledge'})),
            'chapter.fetch': AgentTool('chapter.fetch', 'read', frozenset({'knowledge'})),
            'evidence.search': AgentTool('evidence.search', 'read', frozenset({'knowledge'})),
            'evidence.get': AgentTool('evidence.get', 'read', frozenset({'knowledge'})),
            'source.inspect': AgentTool('source.inspect', 'operate', frozenset({'source_build'})),
            'source.probe': AgentTool('source.probe', 'operate', frozenset({'source_build'})),
            'page.inspect': AgentTool('page.inspect', 'operate', frozenset({'source_build'})),
            'page.request': AgentTool('page.request', 'operate', frozenset({'source_build'})),
            'rule.propose': AgentTool('rule.propose', 'propose', frozenset({'source_build'})),
            'rule.validate': AgentTool('rule.validate', 'operate', frozenset({'source_build'})),
            'source.joint_test': AgentTool(
                'source.joint_test', 'operate', frozenset({'source_build'}),
            ),
            'knowledge.propose': AgentTool(
                'knowledge.propose', 'propose', frozenset({'knowledge', 'novel'}), self._propose_knowledge,
            ),
            'translation.propose': AgentTool('translation.propose', 'propose', frozenset({'knowledge'})),
            'review.request': AgentTool('review.request', 'propose', frozenset({'knowledge', 'source_build'})),
        })
        return tools

    def _authorize(
        self,
        agent_kind: str,
        tool_name: str,
        arguments: dict[str, Any],
        tenant_id: str | None,
    ) -> AgentTool:
        if not isinstance(arguments, dict):
            raise AuthorizationException('tool arguments must be an object')
        if not isinstance(tenant_id, str) or not tenant_id:
            raise AuthorizationException('tenant_id is required')
        self._assert_tenant_scope(arguments, tenant_id)

        tool = self._tools.get(tool_name)
        if tool is None:
            raise AuthorizationException(f'tool is not authorized: {tool_name}')
        if agent_kind not in tool.allowed_agent_kinds:
            raise AuthorizationException(f'agent is not authorized for tool: {tool_name}')
        return tool

    @staticmethod
    def _is_async_handler(handler: Any) -> bool:
        return inspect.iscoroutinefunction(handler) or inspect.iscoroutinefunction(
            getattr(handler, '__call__', None),
        )

    @staticmethod
    def _handler_arguments(tool_name: str, arguments: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        if tool_name != 'source.joint_test':
            return arguments
        return {**arguments, 'tenant_id': tenant_id}

    @staticmethod
    def _propose_knowledge(arguments: dict[str, Any]) -> ToolResult:
        evidence = arguments.get('evidence') or arguments.get('evidence_ids') or arguments.get('evidence_refs')
        if not evidence:
            return ToolResult(status='rejected', error_code='evidence_required')
        return ToolResult(status='accepted', data={'entity': arguments.get('entity'), 'evidence': evidence})

    @classmethod
    def _assert_tenant_scope(cls, value: Any, tenant_id: str | None) -> None:
        for key, nested_value in cls._walk(value):
            if key not in cls._TENANT_ARGUMENT_KEYS:
                continue
            tenant_values = nested_value if isinstance(nested_value, (list, tuple, set)) else (nested_value,)
            if any(candidate != tenant_id for candidate in tenant_values):
                raise AuthorizationException('cross-tenant tool arguments are not allowed')

    @classmethod
    def _walk(cls, value: Any):
        if isinstance(value, Mapping):
            for key, nested_value in value.items():
                yield key, nested_value
                yield from cls._walk(nested_value)
        elif isinstance(value, (list, tuple, set)):
            for nested_value in value:
                yield from cls._walk(nested_value)
