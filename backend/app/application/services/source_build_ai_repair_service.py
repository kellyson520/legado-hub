from __future__ import annotations

import json
from typing import Any

from app.application.services.agent_tool_registry import AgentToolRegistry
from app.domain.entities.agent_runtime import ToolResult


PROMPT_VERSION = 'source-build-agent/v1'

SYSTEM_PROMPT = f"""You are the candidate-only source-build repair agent ({PROMPT_VERSION}).
Work evidence-first: inspect the known source evidence before proposing any rule. Use page tools
only to understand a public, same-origin HTML or search flow. Propose only standard Legado patch
fields and selectors. After every material rule change, call rule.validate and require successful
search, toc, and content evidence before calling review.request. A successful review request is
the only completion condition.

Never publish, enable, delete, exfiltrate data, call unlisted tools, or modify source identity.
This work is candidate-only. Return no prose or unverified patch as a final answer; use the listed
tools and request candidate review only after full validation."""


class SourceBuildAIRepairService:
    """Runs a bounded evidence-first OpenAI tool loop for candidate-only repairs."""

    PROMPT_VERSION = PROMPT_VERSION
    _MAX_MODEL_TURNS = 4
    _MAX_TOOL_ARGUMENT_CHARS = 16_384

    def __init__(self, *, ai_service, platform, agent_runtime):
        self._ai = ai_service
        self._platform = platform
        self._agent_runtime = agent_runtime

    async def repair(
        self,
        *,
        tenant_id: str,
        run_id: str,
        source_version_id: str,
        url: str,
        model: str | None,
        registry: AgentToolRegistry,
    ) -> dict:
        async def runner():
            messages: list[dict[str, Any]] = [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': json.dumps({
                        'source_version_id': source_version_id,
                        'url': url,
                        'prompt_version': self.PROMPT_VERSION,
                    }, separators=(',', ':')),
                },
            ]
            repair = self._repair_state()
            last: dict[str, Any] = {}

            for _turn in range(self._MAX_MODEL_TURNS):
                last = await self._platform.invoke_chat(
                    provider_group='source_build',
                    model=model or None,
                    payload={
                        'messages': messages,
                        'tools': self._tool_schemas(),
                        'tool_choice': 'auto',
                        'temperature': 0,
                    },
                    quota_scope=('tenant', tenant_id),
                )
                output = last.get('output') or {}
                assistant_message = self._assistant_message(output)
                messages.append(assistant_message)
                calls = self._tool_calls(output, assistant_message)
                if not calls:
                    repair['state'] = 'failed'
                    return {**last, 'repair': repair}

                for call in calls:
                    name, arguments, tool_data, result = await self._run_tool_call(
                        call=call,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        registry=registry,
                    )
                    repair['tool_count'] += 1
                    self._record_repair_evidence(
                        repair=repair,
                        tool_name=name,
                        arguments=arguments,
                        result=result,
                    )
                    messages.append({
                        'role': 'tool',
                        'tool_call_id': str(call.get('id') or ''),
                        'content': json.dumps(tool_data, separators=(',', ':')),
                    })

                    if name == 'review.request' and result.status == 'accepted':
                        repair['state'] = (
                            'validated_for_review'
                            if self._review_is_accepted(repair, result)
                            else 'failed'
                        )
                        return {**last, 'repair': repair}

            repair['state'] = 'budget_exhausted'
            return {**last, 'repair': repair}

        return await self._ai.run_source_build_repair(
            {'source_version_id': source_version_id, 'agent_run_id': run_id, 'url': url, 'model': model},
            actor_id=tenant_id,
            runner=runner,
        )

    async def _run_tool_call(
        self,
        *,
        call: dict[str, Any],
        tenant_id: str,
        run_id: str,
        registry: AgentToolRegistry,
    ) -> tuple[str, dict[str, Any], dict[str, Any], ToolResult]:
        function = call.get('function') or {}
        name = str(function.get('name') or '')
        arguments, argument_error = self._tool_arguments(function.get('arguments'))
        tool = registry.get(name)
        invocation = self._agent_runtime.record_tool_invocation(
            run_id=run_id,
            tenant_id=tenant_id,
            tool_name=name,
            category=tool.category if tool else 'operate',
            arguments=arguments,
        )

        if argument_error is not None:
            result = ToolResult(status='rejected', error_code=argument_error)
        else:
            try:
                result = await registry.ainvoke(
                    agent_kind='source_build',
                    tool_name=name,
                    arguments=arguments,
                    tenant_id=tenant_id,
                )
            except Exception:
                result = ToolResult(status='rejected', error_code='tool_execution_failed')

        self._agent_runtime.record_tool_result(
            invocation_id=invocation.id,
            tenant_id=tenant_id,
            status=result.status,
            data=result.data,
            error_code=result.error_code,
        )
        return name, arguments, {
            'status': result.status,
            'data': result.data,
            'error_code': result.error_code,
        }, result

    @staticmethod
    def _assistant_message(output: dict[str, Any]) -> dict[str, Any]:
        message = output.get('message')
        if isinstance(message, dict):
            return message
        return {'role': 'assistant', 'content': str(output.get('text') or '')}

    @staticmethod
    def _tool_calls(output: dict[str, Any], message: dict[str, Any]) -> list[dict[str, Any]]:
        calls = output.get('tool_calls') or message.get('tool_calls') or []
        return [call for call in calls if isinstance(call, dict)] if isinstance(calls, list) else []

    @classmethod
    def _tool_arguments(cls, raw_arguments: Any) -> tuple[dict[str, Any], str | None]:
        if not isinstance(raw_arguments, str) or len(raw_arguments) > cls._MAX_TOOL_ARGUMENT_CHARS:
            return {}, 'invalid_tool_arguments'
        try:
            arguments = json.loads(raw_arguments or '{}')
        except json.JSONDecodeError:
            return {}, 'invalid_tool_arguments'
        if not isinstance(arguments, dict):
            return {}, 'invalid_tool_arguments'
        return arguments, None

    @classmethod
    def _repair_state(cls) -> dict[str, Any]:
        return {
            'state': 'running',
            'patch': None,
            'validation': None,
            'review': None,
            'prompt_version': cls.PROMPT_VERSION,
            'tool_count': 0,
        }

    @classmethod
    def _record_repair_evidence(
        cls,
        *,
        repair: dict[str, Any],
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> None:
        if result.status != 'accepted':
            return
        if tool_name == 'rule.propose' and isinstance(arguments.get('patch'), dict):
            repair['patch'] = arguments['patch']
        elif tool_name == 'rule.validate' and isinstance(result.data, dict):
            repair['validation'] = result.data
            if isinstance(arguments.get('patch'), dict):
                repair['patch'] = arguments['patch']
        elif tool_name == 'review.request' and isinstance(result.data, dict):
            repair['review'] = result.data

    @classmethod
    def _review_is_accepted(cls, repair: dict[str, Any], result: ToolResult) -> bool:
        return result.status == 'accepted' and cls._full_validation_passed(repair.get('validation'))

    @staticmethod
    def _full_validation_passed(validation: Any) -> bool:
        return isinstance(validation, dict) and all(
            isinstance(validation.get(stage), dict) and validation[stage].get('passed') is True
            for stage in ('search', 'toc', 'content')
        )

    @staticmethod
    def _tool_schemas() -> list[dict[str, Any]]:
        string_values = {'type': 'object', 'additionalProperties': {'type': 'string'}}
        patch = {
            'type': 'object',
            'properties': {
                'searchUrl': {'type': 'string'},
                'header': {
                    'anyOf': [
                        {'type': 'string'},
                        {'type': 'object', 'additionalProperties': {'type': 'string'}},
                    ],
                },
                'ruleSearch': string_values,
                'ruleBookInfo': string_values,
                'ruleToc': string_values,
                'ruleContent': string_values,
                'replaceRule': {'type': 'string'},
            },
            'additionalProperties': False,
            'minProperties': 1,
        }

        def schema(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None):
            parameters: dict[str, Any] = {
                'type': 'object',
                'properties': properties,
                'additionalProperties': False,
            }
            if required:
                parameters['required'] = required
            return {
                'type': 'function',
                'function': {'name': name, 'description': description, 'parameters': parameters},
            }

        return [
            schema('source.inspect', 'Read the known candidate source rule and bounded evidence.', {}),
            schema('page.inspect', 'Inspect one public same-origin page with GET.', {
                'url': {'type': 'string', 'minLength': 1},
            }, ['url']),
            schema('page.request', 'Request one public same-origin GET or form POST.', {
                'url': {'type': 'string', 'minLength': 1},
                'method': {'type': 'string', 'enum': ['GET', 'POST']},
                'form': string_values,
            }, ['url', 'method']),
            schema('source.probe', 'Read the most recent bounded full-chain probe summary.', {}),
            schema('rule.propose', 'Store a candidate-only patch restricted to Legado rule fields.', {
                'patch': patch,
            }, ['patch']),
            schema('rule.validate', 'Validate the proposed patch against search, toc, and content.', {
                'patch': patch,
            }),
            schema('review.request', 'Request candidate review after full validation succeeds.', {
                'reason': {'type': 'string', 'maxLength': 500},
            }),
        ]
