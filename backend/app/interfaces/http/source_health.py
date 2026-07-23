from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Literal

from app.core.permissions import Permission
from app.core.response import from_paginated_result, ok
from app.infrastructure.persistence.factory import build_source_health_admin_service
from app.interfaces.http.deps import require_permission


router = APIRouter()
ProbeMode = Literal["full_chain", "search_only"]


class ProbeRequest(BaseModel):
    keyword_samples: list[str] = ["捞尸人", "斗罗大陆", "剑来"]
    probe_mode: ProbeMode = "full_chain"


class ProbeBatchRequest(BaseModel):
    source_ids: list[int]
    keyword_samples: list[str] = ["捞尸人", "斗罗大陆", "剑来"]
    probe_mode: ProbeMode = "full_chain"


class QuarantineRequest(BaseModel):
    note: str = "manual_quarantine"


@router.get("/book-sources")
async def list_book_source_health(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    statuses: str | None = None,
    search: str = Query(default="", max_length=200),
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_health_admin_service()
    try:
        data = await service.list_book_source_health(
            page=page,
            page_size=page_size,
            statuses=statuses.split(",") if statuses else None,
            search=search,
        )
    finally:
        await service.aclose()
    return from_paginated_result(data, message="source health listed")


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
    return ok(data=data, message="source health loaded", meta={})


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
    return ok(data=data, message="source probed", meta={})


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
    return ok(
        data=data["results"],
        message="source probe batch completed",
        meta={"total": data["total"]},
    )


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
    return ok(data=data, message="source recovered", meta={})


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
    return ok(data=data, message="source quarantined", meta={})
