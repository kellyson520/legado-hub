import json
from types import SimpleNamespace

import pytest


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        'id': f'call-{name}',
        'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(arguments)},
    }


class ScriptedPlatform:
    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def invoke_chat(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class ImmediateAIService:
    async def run_source_build_repair(self, _payload, *, actor_id, runner):
        assert actor_id == 'tenant-1'
        return await runner()


class RecordingAgentRuntime:
    def __init__(self):
        self.invocations: list[dict] = []
        self.results: list[dict] = []

    def record_tool_invocation(self, **kwargs):
        self.invocations.append(kwargs)
        return SimpleNamespace(id=f"invocation-{len(self.invocations)}")

    def record_tool_result(self, **kwargs):
        self.results.append(kwargs)


def _response(call: dict | None) -> dict:
    tool_calls = [] if call is None else [call]
    return {
        'provider_name': 'scripted-openai',
        'model': 'scripted-model',
        'output': {
            'message': {'role': 'assistant', 'tool_calls': tool_calls},
            'tool_calls': tool_calls,
        },
        'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2},
    }


@pytest.mark.asyncio
async def test_repair_loop_inspects_proposes_validates_and_requests_review():
    from app.application.services.agent_tool_registry import AgentToolRegistry
    from app.application.services.source_build_ai_repair_service import SourceBuildAIRepairService
    from app.domain.entities.agent_runtime import ToolResult

    patch = {'searchUrl': 'https://books.test/search?q={{key}}'}
    validation = {
        'search': {'passed': True, 'evidence': 'book found'},
        'toc': {'passed': True, 'evidence': 'chapter found'},
        'content': {'passed': True, 'evidence': 'content found'},
    }

    async def accepted(data):
        return ToolResult(status='accepted', data=data)

    registry = AgentToolRegistry(source_build_handlers={
        'source.inspect': lambda _arguments: accepted({'source_rule': {}}),
        'rule.propose': lambda _arguments: accepted({'patch_fields': ['searchUrl']}),
        'rule.validate': lambda _arguments: accepted(validation),
        'review.request': lambda _arguments: accepted({'review_id': 'review-1'}),
    })
    platform = ScriptedPlatform([
        _response(_tool_call('source.inspect', {})),
        _response(_tool_call('rule.propose', {'patch': patch})),
        _response(_tool_call('rule.validate', {})),
        _response(_tool_call('review.request', {'reason': 'full chain passed'})),
    ])
    runtime = RecordingAgentRuntime()
    repair_service = SourceBuildAIRepairService(
        ai_service=ImmediateAIService(), platform=platform, agent_runtime=runtime,
    )

    result = await repair_service.repair(
        tenant_id='tenant-1', run_id='run-1', source_version_id='source-1',
        url='https://books.test/', model='scripted-model', registry=registry,
    )

    assert result['repair'] == {
        'state': 'validated_for_review',
        'patch': patch,
        'validation': validation,
        'review': {'review_id': 'review-1'},
        'prompt_version': 'source-build-agent/v1',
        'tool_count': 4,
    }
    assert [item['tool_name'] for item in runtime.invocations] == [
        'source.inspect', 'rule.propose', 'rule.validate', 'review.request',
    ]
    assert [item['status'] for item in runtime.results] == ['accepted'] * 4

    payload = platform.calls[0]['payload']
    assert platform.calls[0]['provider_group'] == 'source_build'
    assert 'evidence-first' in payload['messages'][0]['content'].lower()
    assert 'never publish' in payload['messages'][0]['content'].lower()
    assert 'no prose' in payload['messages'][0]['content'].lower()
    schemas = {item['function']['name']: item['function']['parameters'] for item in payload['tools']}
    assert set(schemas) == {
        'source.inspect', 'page.inspect', 'page.request', 'source.probe',
        'rule.propose', 'rule.validate', 'review.request',
    }
    assert all(schema['additionalProperties'] is False for schema in schemas.values())
    assert set(schemas['page.request']['properties']) == {'url', 'method', 'form'}


@pytest.mark.asyncio
async def test_repair_loop_does_not_mark_full_validation_as_reviewed_without_review_acceptance():
    from app.application.services.agent_tool_registry import AgentToolRegistry
    from app.application.services.source_build_ai_repair_service import SourceBuildAIRepairService
    from app.domain.entities.agent_runtime import ToolResult

    patch = {'ruleContent': {'content': '#chapter@text'}}
    validation = {
        'search': {'passed': True},
        'toc': {'passed': True},
        'content': {'passed': True},
    }
    registry = AgentToolRegistry(source_build_handlers={
        'source.inspect': lambda _arguments: ToolResult(status='accepted'),
        'rule.propose': lambda _arguments: ToolResult(status='accepted'),
        'rule.validate': lambda _arguments: ToolResult(status='accepted', data=validation),
    })
    platform = ScriptedPlatform([
        _response(_tool_call('source.inspect', {})),
        _response(_tool_call('rule.propose', {'patch': patch})),
        _response(_tool_call('rule.validate', {})),
        _response(None),
    ])
    repair_service = SourceBuildAIRepairService(
        ai_service=ImmediateAIService(), platform=platform, agent_runtime=RecordingAgentRuntime(),
    )

    result = await repair_service.repair(
        tenant_id='tenant-1', run_id='run-1', source_version_id='source-1',
        url='https://books.test/', model='scripted-model', registry=registry,
    )

    assert result['repair']['state'] == 'failed'
    assert result['repair']['patch'] == patch
    assert result['repair']['validation'] == validation
    assert result['repair']['review'] is None


@pytest.mark.asyncio
async def test_repair_loop_stops_an_accepted_review_without_full_validation_as_failed():
    from app.application.services.agent_tool_registry import AgentToolRegistry
    from app.application.services.source_build_ai_repair_service import SourceBuildAIRepairService
    from app.domain.entities.agent_runtime import ToolResult

    platform = ScriptedPlatform([
        _response(_tool_call('review.request', {'reason': 'incorrectly early'})),
    ])
    repair_service = SourceBuildAIRepairService(
        ai_service=ImmediateAIService(),
        platform=platform,
        agent_runtime=RecordingAgentRuntime(),
    )

    result = await repair_service.repair(
        tenant_id='tenant-1', run_id='run-1', source_version_id='source-1',
        url='https://books.test/', model='scripted-model',
        registry=AgentToolRegistry(source_build_handlers={
            'review.request': lambda _arguments: ToolResult(status='accepted', data={'review_id': 'review-1'}),
        }),
    )

    assert result['repair']['state'] == 'failed'
    assert result['repair']['review'] == {'review_id': 'review-1'}
    assert len(platform.calls) == 1


@pytest.mark.asyncio
async def test_repair_loop_reports_the_patch_passed_to_successful_validation():
    from app.application.services.agent_tool_registry import AgentToolRegistry
    from app.application.services.source_build_ai_repair_service import SourceBuildAIRepairService
    from app.domain.entities.agent_runtime import ToolResult

    proposed_patch = {'searchUrl': 'https://books.test/old?q={{key}}'}
    validated_patch = {'searchUrl': 'https://books.test/new?q={{key}}'}
    validation = {
        'search': {'passed': True},
        'toc': {'passed': True},
        'content': {'passed': True},
    }
    platform = ScriptedPlatform([
        _response(_tool_call('rule.propose', {'patch': proposed_patch})),
        _response(_tool_call('rule.validate', {'patch': validated_patch})),
        _response(_tool_call('review.request', {'reason': 'full chain passed'})),
    ])
    repair_service = SourceBuildAIRepairService(
        ai_service=ImmediateAIService(),
        platform=platform,
        agent_runtime=RecordingAgentRuntime(),
    )

    result = await repair_service.repair(
        tenant_id='tenant-1', run_id='run-1', source_version_id='source-1',
        url='https://books.test/', model='scripted-model',
        registry=AgentToolRegistry(source_build_handlers={
            'rule.propose': lambda _arguments: ToolResult(status='accepted'),
            'rule.validate': lambda _arguments: ToolResult(status='accepted', data=validation),
            'review.request': lambda _arguments: ToolResult(status='accepted', data={'review_id': 'review-1'}),
        }),
    )

    assert result['repair']['state'] == 'validated_for_review'
    assert result['repair']['patch'] == validated_patch
