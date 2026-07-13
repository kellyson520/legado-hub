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

    def __init__(self, source_build_handlers: Mapping[str, Any] | None = None):
        tools = self._builtin_tools()
        allowed_handlers = frozenset({
            'source.inspect', 'source.probe', 'rule.propose', 'rule.validate', 'review.request',
        })
        for name, handler in (source_build_handlers or {}).items():
            if name not in allowed_handlers or name not in tools or not callable(handler):
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
        if tool.handler is None:
            return ToolResult(status='rejected', error_code='tool_not_implemented')
        return tool.handler(arguments)

    def get(self, tool_name: str) -> AgentTool | None:
        return self._tools.get(tool_name)

    def list_tools(self) -> tuple[AgentTool, ...]:
        return tuple(self._tools.values())

    def _builtin_tools(self) -> dict[str, AgentTool]:
        tools: dict[str, AgentTool] = {}
        read_tools = (
            'work.search', 'work.get', 'toc.get', 'chapter.get',
            'character.find', 'character.relations',
            'plot.find', 'plot.timeline', 'plot.thread',
            'world.find', 'world.relations', 'world.rules',
            'evidence.search', 'evidence.get',
        )
        for name in read_tools:
            tools[name] = AgentTool(name, 'read', frozenset({'knowledge', 'source_build'}))

        tools.update({
            'source.search': AgentTool('source.search', 'read', frozenset({'source_build'})),
            'source.inspect': AgentTool('source.inspect', 'operate', frozenset({'source_build'})),
            'source.probe': AgentTool('source.probe', 'operate', frozenset({'source_build'})),
            'rule.propose': AgentTool('rule.propose', 'propose', frozenset({'source_build'})),
            'rule.validate': AgentTool('rule.validate', 'operate', frozenset({'source_build'})),
            'knowledge.propose': AgentTool(
                'knowledge.propose', 'propose', frozenset({'knowledge'}), self._propose_knowledge,
            ),
            'translation.propose': AgentTool('translation.propose', 'propose', frozenset({'knowledge'})),
            'review.request': AgentTool('review.request', 'propose', frozenset({'knowledge', 'source_build'})),
        })
        return tools

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
