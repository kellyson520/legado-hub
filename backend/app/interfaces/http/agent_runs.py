from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.application.services.agent_tool_registry import AgentToolRegistry
from app.core.exceptions import AuthorizationException
from app.infrastructure.persistence.factory import build_agent_runtime_service
from app.interfaces.http.deps import ApiKeyIdentity, get_api_key_identity


router = APIRouter()


class CreateAgentRunRequest(BaseModel):
    agent_kind: str = Field(min_length=1, max_length=80)
    input_payload: dict = Field(default_factory=dict)


def _tenant_id(identity: ApiKeyIdentity) -> str:
    return f'api-key:{identity.api_key_id}'


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_history(history) -> list[dict]:
    return [
        {
            'id': invocation.id,
            'tool_name': invocation.tool_name,
            'category': invocation.category,
            'arguments': invocation.arguments,
            'created_at': _timestamp(invocation.created_at),
            'result': (
                {
                    'id': invocation.result.id,
                    'status': invocation.result.status,
                    'data': invocation.result.data,
                    'error_code': invocation.result.error_code,
                    'created_at': _timestamp(invocation.result.created_at),
                }
                if invocation.result is not None
                else None
            ),
            'evidence': [
                {
                    'id': evidence.id,
                    'evidence_type': evidence.evidence_type,
                    'resource_id': evidence.resource_id,
                    'payload': evidence.payload,
                    'created_at': _timestamp(evidence.created_at),
                }
                for evidence in invocation.evidence
            ],
        }
        for invocation in history
    ]


def _serialize_run(run, *, tool_history: list[dict] | None = None) -> dict:
    data = {
        'id': run.id,
        'agent_kind': run.agent_kind,
        'input_payload': run.input_payload,
        'request_metadata': run.request_metadata,
        'status': run.status,
        'created_at': _timestamp(run.created_at),
    }
    if tool_history is not None:
        data['tool_history'] = tool_history
    return data


def _assert_permission(identity: ApiKeyIdentity, permission: str) -> None:
    if permission not in identity.permissions:
        raise AuthorizationException(f'Permission denied: {permission}')


def _allowed_agent_kinds() -> set[str]:
    return {
        agent_kind
        for tool in AgentToolRegistry().list_tools()
        for agent_kind in tool.allowed_agent_kinds
    }


@router.post('/agent-runs')
async def create_agent_run(
    payload: CreateAgentRunRequest,
    identity: ApiKeyIdentity = Depends(get_api_key_identity),
):
    _assert_permission(identity, 'agent_runs.write')
    if payload.agent_kind not in _allowed_agent_kinds():
        raise HTTPException(status_code=422, detail='Unsupported agent kind')
    run = build_agent_runtime_service().create_run(
        tenant_id=_tenant_id(identity),
        agent_kind=payload.agent_kind,
        input_payload=payload.input_payload,
    )
    return {
        'success': True,
        'code': 'OK',
        'message': 'agent run created',
        'data': _serialize_run(run),
        'meta': {},
        'trace_id': None,
    }


@router.get('/agent-runs/{run_id}')
async def get_agent_run(
    run_id: str,
    identity: ApiKeyIdentity = Depends(get_api_key_identity),
):
    _assert_permission(identity, 'agent_runs.read')
    service = build_agent_runtime_service()
    tenant_id = _tenant_id(identity)
    run = service.get_run(run_id, tenant_id=tenant_id)
    if run is None:
        raise HTTPException(status_code=404, detail='Agent run not found')
    history = service.get_tool_history(run_id, tenant_id=tenant_id) or []
    return {
        'success': True,
        'code': 'OK',
        'message': 'agent run retrieved',
        'data': _serialize_run(run, tool_history=_serialize_history(history)),
        'meta': {},
        'trace_id': None,
    }
