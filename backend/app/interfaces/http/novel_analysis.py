import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import (
    build_evidence_service,
    build_canonical_content_repository,
    build_narrative_knowledge_service,
    build_novel_analysis_pipeline_service,
    build_novel_analysis_task_service,
    build_source_repository,
    build_system_settings_service,
)
from app.interfaces.http.deps import require_permission


router = APIRouter()


class CreateAnalysisTaskRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=50)


def _envelope(message: str, data: dict):
    return {"success": True, "code": "OK", "message": message, "data": data, "meta": {}, "trace_id": None}


@router.get("/works/{work_id}/snapshot")
async def get_work_snapshot(
    work_id: str,
    chapter_limit: int = Query(default=8, ge=1, le=24),
    _=Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    return _envelope(
        "work snapshot loaded",
        build_narrative_knowledge_service().build_work_snapshot(work_id, chapter_limit=chapter_limit),
    )


@router.get("/evidence/{evidence_id}")
async def get_evidence(
    evidence_id: str,
    _=Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    try:
        data = build_evidence_service().get_verified_evidence_or_raise(evidence_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        source_id = int(data["source_id"])
    except (TypeError, ValueError):
        source_id = None
    if source_id is not None:
        sources = await build_source_repository().list_book_sources_full(ids=[source_id])
        data["source_name"] = sources[0]["bookSourceName"] if sources else ""
    else:
        data["source_name"] = ""
    return _envelope("evidence loaded", data)


def _task_data(task) -> dict:
    return {
        "id": task.id,
        "work_id": task.work_id,
        "status": task.status,
        "checkpoint": task.checkpoint,
        "tool_call_count": task.tool_call_count,
        "policy": task.policy,
    }


def _safe_task_error(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(
        r"(?i)(authorization\s*:\s*bearer|bearer|api[_ -]?key)\s*[:=]?\s*[^\s,;]+",
        r"\1 [redacted]",
        message,
    )
    return message[:500] or exc.__class__.__name__


@router.get("/works/{work_id}/tasks")
async def list_work_tasks(
    work_id: str,
    identity=Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    tasks = build_novel_analysis_task_service().list_for_work(
        work_id,
        tenant_id=str(identity.user_id),
    )
    return _envelope("analysis tasks loaded", {"items": [_task_data(task) for task in tasks]})


@router.post("/works/{work_id}/tasks")
async def create_work_task(
    work_id: str,
    payload: CreateAnalysisTaskRequest,
    identity=Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    canonical_repo = build_canonical_content_repository()
    if canonical_repo.get_work(work_id) is None:
        raise HTTPException(status_code=404, detail="work not found")
    evidence_service = build_evidence_service()
    for evidence_id in payload.evidence_ids:
        span = evidence_service.get_verified_span(evidence_id)
        chapter = (
            canonical_repo.get_canonical_chapter(span.canonical_chapter_id)
            if span is not None
            else None
        )
        if chapter is None or chapter.canonical_work_id != work_id:
            raise HTTPException(status_code=422, detail="evidence must be verified and belong to the selected work")
    budgets = build_system_settings_service().get_section("agents", "budgets")["value"]
    task = build_novel_analysis_task_service().create_task(
        work_id,
        str(identity.user_id),
        payload.goal,
        policy=budgets,
        selected_evidence_ids=payload.evidence_ids,
    )
    return _envelope("analysis task queued", _task_data(task))


@router.post("/tasks/{task_id}/run")
async def run_task_now(
    task_id: str,
    identity=Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    automation = build_system_settings_service().get_section("agents", "automation")["value"]
    if not bool(automation.get("enabled", True)) or bool(automation.get("emergency_pause", False)):
        raise HTTPException(status_code=409, detail="analysis automation is disabled or emergency-paused")
    task_service = build_novel_analysis_task_service()
    try:
        task = task_service.lease(task_id, tenant_id=str(identity.user_id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        result = await build_novel_analysis_pipeline_service().process_task(
            task,
            tenant_id=str(identity.user_id),
        )
        if result.reasons and not result.claim_ids:
            task = task_service.block(task.id, tenant_id=str(identity.user_id), reason="; ".join(result.reasons))
        else:
            task = task_service.complete(task.id, tenant_id=str(identity.user_id), result=result)
    except Exception as exc:
        task = task_service.block(task.id, tenant_id=str(identity.user_id), reason=_safe_task_error(exc))
    return _envelope("analysis task processed", _task_data(task))


@router.post("/tasks/{task_id}/pause")
async def pause_task(
    task_id: str,
    identity=Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    try:
        task = build_novel_analysis_task_service().pause(task_id, tenant_id=str(identity.user_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _envelope("analysis task paused", _task_data(task))


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    identity=Depends(require_permission(Permission.NOVEL_MANAGE)),
):
    try:
        task = build_novel_analysis_task_service().resume(task_id, tenant_id=str(identity.user_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _envelope("analysis task resumed", _task_data(task))
