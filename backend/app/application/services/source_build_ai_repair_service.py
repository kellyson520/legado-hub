from __future__ import annotations

import json
from typing import Any

from app.application.services.agent_tool_registry import AgentToolRegistry


class SourceBuildAIRepairService:
    """Runs a maximum-four-round OpenAI tool loop for candidate-only source repair."""

    def __init__(self, *, ai_service, platform, agent_runtime):
        self._ai = ai_service
        self._platform = platform
        self._agent_runtime = agent_runtime

    async def repair(self, *, tenant_id: str, run_id: str, source_version_id: str, url: str, model: str,
                     registry: AgentToolRegistry) -> dict:
        async def runner():
            messages: list[dict[str, Any]] = [{
                'role': 'system',
                'content': ('Repair only a candidate book source. Call tools to inspect/propose/validate. '
                            'Never publish. Return only {"patch": {...}} after successful validation.'),
            }]
            tools = self._tool_schemas()
            last: dict = {}
            for _ in range(4):
                last = await self._platform.invoke_chat(
                    provider_group='ai', model=model,
                    payload={'messages': messages, 'tools': tools, 'tool_choice': 'auto', 'temperature': 0},
                    quota_scope=('tenant', tenant_id),
                )
                output = last.get('output') or {}
                calls = output.get('tool_calls') or []
                messages.append(output.get('message') or {'role': 'assistant', 'content': output.get('text', '')})
                if not calls:
                    patch = self._parse_patch(output.get('text', ''))
                    return {**last, 'repair': {'patch': patch, 'completed': bool(patch)}}
                for call in calls:
                    function = call.get('function') or {}
                    name = str(function.get('name') or '')
                    try:
                        arguments = json.loads(function.get('arguments') or '{}')
                        if not isinstance(arguments, dict) or len(function.get('arguments') or '') > 16384:
                            raise ValueError('invalid_tool_arguments')
                        tool = registry.get(name)
                        invocation = self._agent_runtime.record_tool_invocation(
                            run_id=run_id, tenant_id=tenant_id, tool_name=name,
                            category=tool.category if tool else 'operate', arguments=arguments,
                        )
                        result = registry.invoke(agent_kind='source_build', tool_name=name, arguments=arguments, tenant_id=tenant_id)
                        self._agent_runtime.record_tool_result(
                            invocation_id=invocation.id, tenant_id=tenant_id, status=result.status,
                            data=result.data, error_code=result.error_code,
                        )
                        tool_data = {'status': result.status, 'data': result.data, 'error_code': result.error_code}
                    except Exception as exc:
                        tool_data = {'status': 'rejected', 'error_code': 'tool_execution_failed', 'message': str(exc)[:300]}
                    messages.append({'role': 'tool', 'tool_call_id': call.get('id', ''), 'content': json.dumps(tool_data)})
            return {**last, 'repair': {'patch': None, 'completed': False, 'error': 'tool_round_limit'}}

        return await self._ai.run_source_build_repair(
            {'source_version_id': source_version_id, 'agent_run_id': run_id, 'url': url, 'model': model},
            actor_id=tenant_id, runner=runner,
        )

    @staticmethod
    def _parse_patch(text: str) -> dict | None:
        try:
            value = json.loads(text)
            return value.get('patch') if isinstance(value, dict) and isinstance(value.get('patch'), dict) else None
        except (TypeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _tool_schemas() -> list[dict]:
        names = ('source.inspect', 'source.probe', 'rule.propose', 'rule.validate', 'review.request')
        return [{'type': 'function', 'function': {'name': name, 'description': name, 'parameters': {'type': 'object'}}} for name in names]
