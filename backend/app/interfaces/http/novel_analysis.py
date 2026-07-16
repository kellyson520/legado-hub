from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import (
    build_evidence_service,
    build_narrative_knowledge_service,
    build_source_repository,
)
from app.interfaces.http.deps import require_permission


router = APIRouter()


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
