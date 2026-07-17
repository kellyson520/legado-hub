import pytest


@pytest.mark.asyncio
async def test_engine_action_response_uses_unified_trace_envelope(monkeypatch):
    from app.core.logging import clear_log_context, set_log_context
    from app.interfaces.http import engine

    class FakeEngineService:
        async def evaluate(self, payload):
            assert payload == {'source': {'ruleContent': {}}}
            return {'score': 100}

    monkeypatch.setattr(engine, 'build_engine_service', lambda: FakeEngineService())
    set_log_context(trace_id='trace-engine-action')
    try:
        response = await engine.evaluate(
            engine.EvaluateRequest(source={'ruleContent': {}}),
            _=None,
        )
    finally:
        clear_log_context()

    assert response == {
        'success': True,
        'code': 'OK',
        'message': 'engine evaluation complete',
        'data': {'score': 100},
        'meta': {},
        'trace_id': 'trace-engine-action',
    }


def test_system_response_uses_the_shared_ok_helper():
    from app.core.logging import clear_log_context, set_log_context
    from app.interfaces.http.system import _system_response

    set_log_context(trace_id='trace-system-action')
    try:
        response = _system_response('settings saved', {'version': 'v2'})
    finally:
        clear_log_context()

    assert response == {
        'success': True,
        'code': 'OK',
        'message': 'settings saved',
        'data': {'version': 'v2'},
        'meta': {},
        'trace_id': 'trace-system-action',
    }


@pytest.mark.asyncio
async def test_agent_run_creation_uses_the_shared_trace_envelope(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from app.core.logging import clear_log_context, set_log_context
    from app.interfaces.http import agent_runs
    from app.interfaces.http.deps import ApiKeyIdentity

    class FakeAgentRuntimeService:
        def create_run(self, **kwargs):
            assert kwargs['tenant_id'] == 'api-key:7'
            return SimpleNamespace(
                id='run-1',
                agent_kind=kwargs['agent_kind'],
                input_payload=kwargs['input_payload'],
                status='candidate',
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    monkeypatch.setattr(agent_runs, '_allowed_agent_kinds', lambda: {'source_build'})
    monkeypatch.setattr(agent_runs, 'build_agent_runtime_service', lambda: FakeAgentRuntimeService())
    set_log_context(trace_id='trace-agent-run')
    try:
        response = await agent_runs.create_agent_run(
            agent_runs.CreateAgentRunRequest(agent_kind='source_build', input_payload={'url': 'https://example.test'}),
            ApiKeyIdentity(7, 'test', {'agent_runs.write'}),
        )
    finally:
        clear_log_context()

    assert response['meta'] == {}
    assert response['trace_id'] == 'trace-agent-run'
