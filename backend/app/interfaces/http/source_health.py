from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_source_health_admin_service
from app.interfaces.http.deps import require_permission


router = APIRouter()


class ProbeRequest(BaseModel):
    keyword_samples: list[str] = ["捞尸人", "斗罗大陆"]
    probe_mode: str = "full_chain"


class ProbeBatchRequest(BaseModel):
    source_ids: list[int]
    keyword_samples: list[str] = ["捞尸人", "斗罗大陆"]
    probe_mode: str = "full_chain"


class QuarantineRequest(BaseModel):
    note: str = "manual_quarantine"


@router.get("/book-sources")
async def list_book_source_health(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    statuses: str | None = None,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_health_admin_service()
    try:
        data = await service.list_book_source_health(
            page=page,
            page_size=page_size,
            statuses=statuses.split(",") if statuses else None,
        )
    finally:
        await service.aclose()
    return {
        "success": True,
        "code": "OK",
        "message": "source health listed",
        "data": data["items"],
        "meta": data["meta"],
        "trace_id": None,
    }


@router.get("/book-sources/{source_id}")
async def get_book_source_health(
    source_id: int,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_health_admin_service()
    try:
        data = await service.get_book_source_health(source_id)
    finally:
        await service.aclose()
    return {
        "success": True,
        "code": "OK",
        "message": "source health loaded",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.post("/book-sources/{source_id}/probe")
async def probe_book_source(
    source_id: int,
    payload: ProbeRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_health_admin_service()
    try:
        data = await service.probe_book_source(
            source_id,
            keyword_samples=payload.keyword_samples,
            probe_mode=payload.probe_mode,
        )
    finally:
        await service.aclose()
    return {
        "success": True,
        "code": "OK",
        "message": "source probed",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.post("/book-sources/probe-batch")
async def probe_book_sources(
    payload: ProbeBatchRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_health_admin_service()
    try:
        data = await service.probe_book_sources(
            payload.source_ids,
            keyword_samples=payload.keyword_samples,
            probe_mode=payload.probe_mode,
        )
    finally:
        await service.aclose()
    return {
        "success": True,
        "code": "OK",
        "message": "source probe batch completed",
        "data": data["results"],
        "meta": {"total": data["total"]},
        "trace_id": None,
    }


@router.post("/book-sources/{source_id}/recover")
async def recover_book_source(
    source_id: int,
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_health_admin_service()
    try:
        data = await service.recover_source(source_id)
    finally:
        await service.aclose()
    return {
        "success": True,
        "code": "OK",
        "message": "source recovered",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.post("/book-sources/{source_id}/quarantine")
async def quarantine_book_source(
    source_id: int,
    payload: QuarantineRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_health_admin_service()
    try:
        data = await service.quarantine_source(source_id, note=payload.note)
    finally:
        await service.aclose()
    return {
        "success": True,
        "code": "OK",
        "message": "source quarantined",
        "data": data,
        "meta": {},
        "trace_id": None,
    }
