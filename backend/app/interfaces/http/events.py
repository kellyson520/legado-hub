import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

from app.core.exceptions import AuthorizationException, NotFoundException, ValidationException
from app.core.pagination import pagination_meta
from app.core.permissions import Permission
from app.core.response import from_paginated_result
from app.application.services.event_delivery_service import get_event_delivery_stream_broker
from app.infrastructure.persistence.factory import (
    build_agent_runtime_service,
    build_event_delivery_service,
    build_job_service,
    build_source_review_service,
    build_source_runtime_service,
    build_translation_service,
    build_work_knowledge_service,
)
from app.interfaces.http.deps import RequestIdentity, get_current_identity, require_permission


router = APIRouter()


class ReviewQueueResolveRequest(BaseModel):
    item_type: str = Field(min_length=1, max_length=80)
    action: str = Field(default='publish', min_length=1, max_length=40)
    memory_note: dict | None = None


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _source_review_evidence(payload: dict, source_url: str) -> str:
    audit_report = payload.get('audit_report')
    if isinstance(audit_report, dict):
        audit_reason = audit_report.get('reason')
        if isinstance(audit_reason, str) and audit_reason.strip():
            return audit_reason.strip()
    reason = payload.get('reason')
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    reason_tags = payload.get('reason_tags')
    if isinstance(reason_tags, list) and reason_tags:
        return ', '.join(str(tag) for tag in reason_tags)
    return source_url


def _review_search_text(values: list[object]) -> str:
    return ' '.join(str(value or '') for value in values).lower()


def _serialize_agent_tool_history(history) -> list[dict]:
    return [
        {
            'id': invocation.id,
            'tool_name': invocation.tool_name,
            'category': invocation.category,
            'arguments': invocation.arguments,
            'created_at': _iso(invocation.created_at),
            'result': (
                {
                    'id': invocation.result.id,
                    'status': invocation.result.status,
                    'data': invocation.result.data,
                    'error_code': invocation.result.error_code,
                    'created_at': _iso(invocation.result.created_at),
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
                    'created_at': _iso(evidence.created_at),
                }
                for evidence in invocation.evidence
            ],
        }
        for invocation in history
    ]


def _serialize_agent_run(run, *, history=None) -> dict:
    invocations = history or []
    evidence_count = sum(len(invocation.evidence) for invocation in invocations)
    accepted_count = sum(1 for invocation in invocations if invocation.result and invocation.result.status == 'accepted')
    rejected_count = sum(1 for invocation in invocations if invocation.result and invocation.result.status == 'rejected')
    latest_tool = invocations[-1].tool_name if invocations else None
    data = {
        'id': run.id,
        'tenant_id': run.tenant_id,
        'agent_kind': run.agent_kind,
        'input_payload': run.input_payload,
        'status': run.status,
        'created_at': _iso(run.created_at),
        'tool_invocation_count': len(invocations),
        'accepted_count': accepted_count,
        'rejected_count': rejected_count,
        'evidence_count': evidence_count,
        'latest_tool_name': latest_tool,
    }
    if history is not None:
        data['tool_history'] = _serialize_agent_tool_history(invocations)
    return data


def _assert_review_queue_write_permission(identity: RequestIdentity, item_type: str) -> None:
    if Permission.AGENT_RUNS_WRITE.value not in identity.permissions:
        raise AuthorizationException(f'Permission denied: {Permission.AGENT_RUNS_WRITE.value}')

    required_permission = {
        'knowledge_proposal': Permission.NOVEL_MANAGE.value,
        'source_version': Permission.ENGINE_DEPLOY.value,
        'source_review': Permission.BOOK_SOURCES_WRITE.value,
        'translation_job': Permission.TRANSLATION_RUN.value,
    }.get(item_type)
    if required_permission is None:
        raise ValidationException('Unsupported review queue item type')
    if required_permission not in identity.permissions:
        raise AuthorizationException(f'Permission denied: {required_permission}')


@router.get('/jobs')
async def list_operations_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=50),
    _=Depends(require_permission(Permission.SYSTEM_JOBS_MANAGE)),
):
    result = build_job_service().list_jobs_page(page=page, page_size=page_size, search=search, status=status)
    data = [
        {
            'id': job.id,
            'kind': job.kind,
            'status': job.status,
            'tenant_id': job.tenant_id,
            'attempt_count': job.attempt_count,
            'created_at': job.created_at.isoformat() if job.created_at is not None else None,
            'last_error': job.last_error,
        }
        for job in result["items"]
    ]
    return from_paginated_result({**result, 'items': data}, message='operations jobs listed')


@router.get('/deliveries')
async def list_event_deliveries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=50),
    _=Depends(require_permission(Permission.SYSTEM_JOBS_MANAGE)),
):
    result = build_event_delivery_service().list_deliveries_page(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
    )
    data = [
        {
            'event_id': delivery.event_id,
            'event_type': delivery.event_type,
            'tenant_id': delivery.tenant_id,
            'target_url': delivery.target_url,
            'dedupe_key': delivery.dedupe_key,
            'status': delivery.status,
            'attempt_count': delivery.attempt_count,
            'last_error': delivery.last_error,
            'next_attempt_at': delivery.next_attempt_at.isoformat() if delivery.next_attempt_at is not None else None,
            'delivered_at': delivery.delivered_at.isoformat() if delivery.delivered_at is not None else None,
            'created_at': delivery.created_at.isoformat() if delivery.created_at is not None else None,
        }
        for delivery in result["items"]
    ]
    return from_paginated_result({**result, 'items': data}, message='event deliveries listed')


@router.get('/deliveries/{event_id}/attempts')
async def list_event_delivery_attempts(
    event_id: str,
    _=Depends(require_permission(Permission.SYSTEM_JOBS_MANAGE)),
):
    attempts = build_event_delivery_service().list_attempts(event_id)
    data = [
        {
            'id': attempt.id,
            'event_id': attempt.event_id,
            'attempt_no': attempt.attempt_no,
            'delivered': attempt.delivered,
            'status_code': attempt.status_code,
            'error_message': attempt.error_message,
            'created_at': attempt.created_at.isoformat() if attempt.created_at is not None else None,
        }
        for attempt in attempts
    ]
    return {
        'success': True,
        'code': 'OK',
        'message': 'event delivery attempts listed',
        'data': data,
        'meta': {'total': len(data)},
        'trace_id': None,
    }


@router.get('/source-builds')
async def list_source_build_candidates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    source_runtime = build_source_runtime_service()
    result = await source_runtime.list_recent_versions_page(
        status=['candidate', 'failed'],
        page=page,
        page_size=page_size,
        search=search,
    )
    return from_paginated_result(result, message='source build candidates listed')


@router.get('/agent-runs')
async def list_operations_agent_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    status: str | None = Query(default=None, max_length=50),
    _=Depends(require_permission(Permission.AGENT_RUNS_READ)),
):
    service = build_agent_runtime_service()
    result = service.list_runs_page(page=page, page_size=page_size, search=search, status=status)
    rows = []
    for run in result["items"]:
        history = service.get_tool_history(run.id, tenant_id=run.tenant_id) or []
        rows.append(_serialize_agent_run(run, history=history))
    return from_paginated_result({**result, 'items': rows}, message='agent runs listed')


@router.get('/agent-runs/{run_id}')
async def get_operations_agent_run(
    run_id: str,
    _=Depends(require_permission(Permission.AGENT_RUNS_READ)),
):
    service = build_agent_runtime_service()
    run = service.get_run_admin(run_id)
    if run is None:
        raise NotFoundException('Agent run not found')
    history = service.get_tool_history(run.id, tenant_id=run.tenant_id) or []
    return {
        'success': True,
        'code': 'OK',
        'message': 'agent run retrieved',
        'data': _serialize_agent_run(run, history=history),
        'meta': {},
        'trace_id': None,
    }


@router.get('/review-queue')
async def list_review_queue(
    page: int = Query(default=1, ge=1, le=100),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str = Query(default="", max_length=200),
    _=Depends(require_permission(Permission.AGENT_RUNS_READ)),
):
    query_limit = page * page_size
    knowledge_result = build_work_knowledge_service().list_review_queue_page(
        page=1,
        page_size=query_limit,
        search=search,
    )
    source_build_result = await build_source_runtime_service().list_recent_versions_page(
        status='candidate',
        page=1,
        page_size=query_limit,
        search=search,
    )
    source_review_result = build_source_review_service().list_review_queue_page(
        page=1,
        page_size=query_limit,
        search=search,
    )
    items = knowledge_result["items"]
    source_build_candidates = source_build_result["items"]
    source_review_items = source_review_result["items"]
    data = [
        {
            'id': item.id,
            'item_type': 'knowledge_proposal',
            'work_id': item.work_id,
            'source_chapter_id': item.source_chapter_id,
            'proposal_type': item.proposal_type,
            'subject': item.subject,
            'relation': item.relation,
            'object_name': item.object_name,
            'evidence': item.evidence,
            'summary': f'{item.subject} {item.relation} {item.object_name}'.strip() or item.proposal_type,
            'payload': item.payload,
            'status': item.status,
            'created_by': item.created_by,
            'reviewed_by': item.reviewed_by,
            'created_at': item.created_at.isoformat() if item.created_at else None,
            'published_at': item.published_at.isoformat() if item.published_at else None,
            '_search_fields': [
                item.id,
                item.work_id,
                item.source_chapter_id,
                item.proposal_type,
                item.subject,
                item.relation,
                item.object_name,
                item.evidence,
                item.created_by,
            ],
        }
        for item in items
    ]
    data.extend(
        {
            'id': item['id'],
            'item_type': 'source_version',
            'work_id': item['payload'].get('keyword') or None,
            'source_chapter_id': item['id'],
            'proposal_type': 'source_version_publish',
            'subject': item['source_type'],
            'relation': 'publish',
            'object_name': item['source_id'],
            'evidence': item['payload'].get('canonical_url') or item['source_id'],
            'summary': (
                f"Publish source candidate"
                + (
                    f" (grade {item['latest_run']['grade']})"
                    if item.get('latest_run') and item['latest_run'].get('grade')
                    else ''
                )
            ),
            'payload': item['payload'] | {'latest_run': item.get('latest_run')},
            'status': item['status'],
            'created_by': item['created_by'],
            'reviewed_by': None,
            'created_at': item['created_at'],
            'published_at': None,
            '_search_fields': [
                item['id'],
                item['source_type'],
                item['source_id'],
                item['created_by'],
                json.dumps(item['payload'], ensure_ascii=False),
            ],
        }
        for item in source_build_candidates
    )
    data.extend(
        {
            'id': item.id,
            'item_type': 'source_review',
            'work_id': item.source_version_id,
            'source_chapter_id': item.source_version_id or item.id,
            'proposal_type': item.review_type,
            'subject': item.review_type,
            'relation': 'review',
            'object_name': item.source_url,
            'evidence': _source_review_evidence(item.payload, item.source_url),
            'summary': item.summary,
            'payload': item.payload,
            'status': item.status,
            'created_by': item.created_by,
            'reviewed_by': item.reviewed_by,
            'created_at': _iso(item.created_at),
            'published_at': None,
            '_search_fields': [
                item.id,
                item.review_type,
                item.source_version_id,
                item.source_url,
                item.summary,
                item.created_by,
                json.dumps(item.payload, ensure_ascii=False),
            ],
        }
        for item in source_review_items
    )
    translation_result = await build_translation_service().list_jobs_page(
        page=1,
        page_size=query_limit,
        search=search,
        review_status='candidate',
    )
    translation_jobs = translation_result["items"]
    data.extend(
        {
            'id': job['id'],
            'item_type': 'translation_job',
            'work_id': None,
            'source_chapter_id': job.get('content_variant_id'),
            'proposal_type': 'translation_review',
            'subject': f"{job.get('source_language', '')} -> {job.get('target_language', '')}",
            'relation': 'review',
            'object_name': job.get('content_variant_id'),
            'evidence': (job.get('result_text') or job.get('source_text') or '').strip() or 'Translation review pending',
            'summary': f"Translation memory review ({job.get('chunk_count', 0)} chunks)",
            'payload': {
                'provider': job.get('provider'),
                'model': job.get('model'),
                'chunk_count': job.get('chunk_count', 0),
                'content_variant_id': job.get('content_variant_id'),
                'memory_payload': job.get('memory_payload', {}),
            },
            'status': job.get('review_status', 'candidate'),
            'created_by': job.get('actor_id'),
            'reviewed_by': None,
            'created_at': job.get('created_at'),
            'published_at': None,
            '_search_fields': [
                job.get('id'),
                job.get('actor_id'),
                job.get('source_language'),
                job.get('target_language'),
                job.get('provider'),
                job.get('model'),
                job.get('source_text'),
                job.get('result_text'),
                job.get('content_variant_id'),
                json.dumps(job.get('memory_payload', {}), ensure_ascii=False),
            ],
        }
        for job in translation_jobs
    )
    data.sort(key=lambda item: item.get('created_at') or '', reverse=True)
    normalized_search = search.strip().lower()
    if normalized_search:
        data = [item for item in data if normalized_search in _review_search_text(item['_search_fields'])]
    for item in data:
        item.pop('_search_fields', None)
    total = (
        knowledge_result["meta"]["total"]
        + source_build_result["meta"]["total"]
        + source_review_result["meta"]["total"]
        + translation_result["meta"]["total"]
    )
    data = data[(page - 1) * page_size : page * page_size]
    return from_paginated_result(
        {
            'items': data,
            'meta': pagination_meta(page, page_size, total, search=search),
        },
        message='review queue listed',
    )


@router.post('/review-queue/{item_id}/resolve')
async def resolve_review_queue_item(
    item_id: str,
    payload: ReviewQueueResolveRequest,
    identity: RequestIdentity = Depends(get_current_identity),
):
    _assert_review_queue_write_permission(identity, payload.item_type)

    if payload.item_type == 'knowledge_proposal':
        proposal = build_work_knowledge_service().resolve_review(
            item_id,
            action=payload.action,
            reviewer_id=str(identity.user_id),
        )
        data = {
            'queue_item_id': item_id,
            'result_id': proposal.id,
            'item_type': payload.item_type,
            'status': proposal.status,
            'action': payload.action,
            'reviewed_by': proposal.reviewed_by,
            'published_at': _iso(proposal.published_at),
        }
    elif payload.item_type == 'source_version':
        result = await build_source_runtime_service().resolve_review(
            item_id,
            reviewer_id=str(identity.user_id),
            action=payload.action,
        )
        data = {
            'queue_item_id': item_id,
            'result_id': result['source_version_id'],
            'item_type': payload.item_type,
            'status': result['status'],
            'action': result['review_action'],
            'reviewed_by': result['reviewed_by'],
            'published_at': result['published_at'],
        }
    elif payload.item_type == 'source_review':
        result = build_source_review_service().resolve_review(
            item_id,
            reviewer_id=str(identity.user_id),
            action=payload.action,
        )
        data = {
            'queue_item_id': item_id,
            'result_id': result.id,
            'item_type': payload.item_type,
            'status': result.status,
            'action': payload.action,
            'reviewed_by': result.reviewed_by,
            'published_at': None,
            'resolved_at': _iso(result.resolved_at),
        }
    else:
        review_note = payload.memory_note or {
            'source': 'operations.review_queue',
            'action': payload.action,
        }
        result = await build_translation_service().review_job(
            item_id,
            reviewer_id=str(identity.user_id),
            memory_note=review_note,
        )
        data = {
            'queue_item_id': item_id,
            'result_id': result['id'],
            'item_type': payload.item_type,
            'status': result['review_status'],
            'action': payload.action,
            'reviewed_by': result['memory_payload'].get('reviewed_by'),
            'published_at': None,
        }

    return {
        'success': True,
        'code': 'OK',
        'message': 'review queue item resolved',
        'data': data,
        'meta': {},
        'trace_id': None,
    }


@router.get('/stream')
async def stream_event_deliveries(
    request: Request,
    tenant_id: str | None = None,
    once: bool = False,
    limit: int = 20,
    _=Depends(require_permission(Permission.SYSTEM_JOBS_MANAGE)),
):
    service = build_event_delivery_service()
    broker = get_event_delivery_stream_broker()

    def encode(item) -> str:
        payload = json.dumps(item.data, ensure_ascii=False, separators=(',', ':'))
        return f'id: {item.id}\nevent: {item.event}\ndata: {payload}\n\n'

    async def iterator():
        for item in service.list_stream_events(tenant_id=tenant_id, limit=limit):
            yield encode(item)
        if once:
            return

        subscriber_id, queue = broker.subscribe(tenant_id=tenant_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    yield ': keep-alive\n\n'
                    continue
                yield encode(item)
        finally:
            broker.unsubscribe(subscriber_id)

    return StreamingResponse(iterator(), media_type='text/event-stream')
