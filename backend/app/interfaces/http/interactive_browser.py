import asyncio
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.application.services.interactive_browser_service import InteractiveBrowserUnavailableError
from app.application.services.source_build_audit_service import ManualBrowserValidationRecoveryPending
from app.core.config import settings
from app.core.permissions import Permission
from app.infrastructure.persistence.factory import (
    build_interactive_browser_service,
    build_source_build_audit_service,
    build_source_runtime_repository,
)
from app.interfaces.http.deps import RequestIdentity, get_current_identity, require_permission


router = APIRouter()


def _serialize(session) -> dict:
    return {
        'id': session.id,
        'source_version_id': session.source_version_id,
        'state': session.state.value,
        'target_origin': session.allowed_origins[0] if session.allowed_origins else None,
        'expires_at': session.expires_at.isoformat() if session.expires_at is not None else None,
        'closed_at': session.closed_at.isoformat() if session.closed_at is not None else None,
        'terminal_reason': session.terminal_reason,
    }


def _response(message: str, data: dict) -> dict:
    return {
        'success': True,
        'code': 'OK',
        'message': message,
        'data': data,
        'meta': {},
        'trace_id': None,
    }


@router.get('/sessions/{session_id}')
async def get_interactive_browser_session(
    session_id: str,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_TEST)),
):
    session = await build_interactive_browser_service().get_for_owner(session_id, owner_id=str(identity.user_id))
    if session is None:
        raise HTTPException(status_code=404, detail='Interactive browser session not found')
    return _response('interactive browser session loaded', _serialize(session))


@router.delete('/sessions/{session_id}')
async def cancel_interactive_browser_session(
    session_id: str,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_TEST)),
):
    service = build_interactive_browser_service()
    try:
        session = await service.cancel(session_id, owner_id=str(identity.user_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Interactive browser session not found') from exc
    except InteractiveBrowserUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _response('interactive browser session cancelled', _serialize(session))


@router.post('/sessions/{session_id}/continue')
async def continue_interactive_browser_validation(
    session_id: str,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_TEST)),
):
    service = build_interactive_browser_service()
    owner_id = str(identity.user_id)
    session = await service.get_for_owner(session_id, owner_id=owner_id)
    if session is None:
        raise HTTPException(status_code=404, detail='Interactive browser session not found')
    version = build_source_runtime_repository().get_version(session.source_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail='Source version not found')
    source_rule = version.payload.get('source_rule') if isinstance(version.payload, dict) else None
    if not isinstance(source_rule, dict):
        raise HTTPException(status_code=422, detail='Source version has no candidate rule')
    audit_result = {}

    def accept_manual_browser_validation(validation):
        try:
            audit_result['value'] = build_source_build_audit_service().accept_manual_browser_validation(
                version.id,
                browser_session_id=session_id,
                validation=validation,
            )
        except ManualBrowserValidationRecoveryPending as outcome:
            audit_result['value'] = outcome.audit_result
            audit_result['recovery_pending'] = True

    try:
        validation = await service.continue_validation(
            session_id,
            owner_id=owner_id,
            source_rule=source_rule,
            keyword=str(version.payload.get('keyword') or 'sample'),
            on_success=accept_manual_browser_validation,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Interactive browser session not found') from exc
    except InteractiveBrowserUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    recovery_pending = bool(audit_result.get('recovery_pending'))
    response = _response(
        (
            'interactive browser validation checkpoint requires recovery'
            if recovery_pending
            else 'interactive browser validation completed'
        ),
        {
            'session': _serialize(await service.get_for_owner(session_id, owner_id=owner_id) or session),
            'validation': {
                'passed': validation.passed,
                'reason': validation.reason,
                'stages': validation.stages or {},
            },
            'audit': audit_result.get('value'),
            'recovery_pending': recovery_pending,
        },
    )
    if recovery_pending:
        return JSONResponse(status_code=202, content=response)
    return response


@router.post('/sessions/{session_id}/relay-ticket')
async def create_interactive_browser_relay_ticket(
    session_id: str,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.ENGINE_TEST)),
):
    service = build_interactive_browser_service()
    try:
        ticket = await service.issue_relay_ticket(session_id, owner_id=str(identity.user_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Interactive browser session not found') from exc
    except InteractiveBrowserUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    relay_path = f'/api/interactive-browser/sessions/{ticket.session_id}/relay?{urlencode({"token": ticket.token, "owner_id": identity.user_id})}'
    return _response('interactive browser relay ticket issued', {'relay_path': relay_path})


@router.websocket('/sessions/{session_id}/relay')
async def relay_interactive_browser_session(websocket: WebSocket, session_id: str):
    token = str(websocket.query_params.get('token') or '')
    owner_id = str(websocket.query_params.get('owner_id') or '')
    origin = str(websocket.headers.get('origin') or '')
    if origin not in settings.ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return
    service = build_interactive_browser_service()
    try:
        ticket = await service.consume_relay_ticket(token, owner_id=owner_id)
    except Exception:
        await websocket.close(code=1008)
        return
    if ticket.session_id != session_id:
        await websocket.close(code=1008)
        return
    try:
        from websockets.asyncio.client import connect

        upstream = await connect(f'ws://127.0.0.1:{ticket.relay_port}')
    except Exception:
        await websocket.close(code=1011)
        return
    await websocket.accept()

    async def client_to_local() -> None:
        while True:
            message = await websocket.receive()
            if message.get('type') == 'websocket.disconnect':
                return
            if message.get('bytes') is not None:
                await upstream.send(message['bytes'])
            elif message.get('text') is not None:
                await upstream.send(message['text'])

    async def local_to_client() -> None:
        async for message in upstream:
            if isinstance(message, bytes):
                await websocket.send_bytes(message)
            else:
                await websocket.send_text(message)

    tasks = [asyncio.create_task(client_to_local()), asyncio.create_task(local_to_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await upstream.close()
