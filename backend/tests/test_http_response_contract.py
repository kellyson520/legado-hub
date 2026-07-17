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
