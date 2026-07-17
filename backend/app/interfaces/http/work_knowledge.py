from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.core.response import ok
from app.infrastructure.persistence.factory import build_work_knowledge_service
from app.interfaces.http.deps import RequestIdentity, require_permission


router = APIRouter()


class RelationProposalRequest(BaseModel):
    work_id: str = Field(min_length=1, max_length=120)
    source_chapter_id: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1)
    relation: str = Field(min_length=1, max_length=120)


class PlotEventProposalRequest(BaseModel):
    work_id: str = Field(min_length=1, max_length=120)
    source_chapter_id: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1)
    event_title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1)


class WorldRuleProposalRequest(BaseModel):
    work_id: str = Field(min_length=1, max_length=120)
    source_chapter_id: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1)
    rule_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)


class ReviewResolveRequest(BaseModel):
    action: str = Field(default='publish', min_length=1, max_length=40)


def _serialize(item) -> dict:
    return {
        'id': item.id,
        'work_id': item.work_id,
        'source_chapter_id': item.source_chapter_id,
        'proposal_type': item.proposal_type,
        'subject': item.subject,
        'relation': item.relation,
        'object_name': item.object_name,
        'evidence': item.evidence,
        'status': item.status,
        'revision_of': item.revision_of,
        'created_by': item.created_by,
        'reviewed_by': item.reviewed_by,
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'published_at': item.published_at.isoformat() if item.published_at else None,
    }


@router.post('/relations')
async def propose_relation(
    payload: RelationProposalRequest,
    identity: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    proposal = build_work_knowledge_service().propose_relation(
        work_id=payload.work_id,
        source_chapter_id=payload.source_chapter_id,
        evidence=payload.evidence,
        relation=payload.relation,
        actor_id=str(identity.user_id),
    )
    return ok(data=_serialize(proposal), message='knowledge proposal created', meta={})


@router.post('/plot-events')
async def propose_plot_event(
    payload: PlotEventProposalRequest,
    identity: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    proposal = build_work_knowledge_service().propose_plot_event(
        work_id=payload.work_id,
        source_chapter_id=payload.source_chapter_id,
        evidence=payload.evidence,
        event_title=payload.event_title,
        summary=payload.summary,
        actor_id=str(identity.user_id),
    )
    return ok(data=_serialize(proposal), message='plot proposal created', meta={})


@router.post('/world-rules')
async def propose_world_rule(
    payload: WorldRuleProposalRequest,
    identity: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    proposal = build_work_knowledge_service().propose_world_rule(
        work_id=payload.work_id,
        source_chapter_id=payload.source_chapter_id,
        evidence=payload.evidence,
        rule_name=payload.rule_name,
        description=payload.description,
        actor_id=str(identity.user_id),
    )
    return ok(data=_serialize(proposal), message='world rule proposal created', meta={})


@router.get('/works/{work_id}/relations')
async def list_published_relations(
    work_id: str,
    _: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    items = build_work_knowledge_service().list_published_relations(work_id)
    data = [_serialize(item) for item in items]
    return ok(data=data, message='published relations listed', meta={'total': len(data)})


@router.get('/works/{work_id}/plot-events')
async def list_published_plot_events(
    work_id: str,
    _: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    items = build_work_knowledge_service().list_published_plot_events(work_id)
    data = [_serialize(item) for item in items]
    return ok(data=data, message='published plot events listed', meta={'total': len(data)})


@router.get('/works/{work_id}/world-rules')
async def list_published_world_rules(
    work_id: str,
    _: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    items = build_work_knowledge_service().list_published_world_rules(work_id)
    data = [_serialize(item) for item in items]
    return ok(data=data, message='published world rules listed', meta={'total': len(data)})


@router.post('/reviews/{proposal_id}/resolve')
async def resolve_review(
    proposal_id: str,
    payload: ReviewResolveRequest,
    identity: RequestIdentity = Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    proposal = build_work_knowledge_service().resolve_review(
        proposal_id,
        action=payload.action,
        reviewer_id=str(identity.user_id),
    )
    return ok(data=_serialize(proposal), message='knowledge review resolved', meta={})
