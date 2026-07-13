from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import build_source_runtime_service, build_source_service
from app.interfaces.http.deps import RequestIdentity, get_current_identity, require_permission


router = APIRouter()


class BookSourcePayload(BaseModel):
    bookSourceName: str
    bookSourceUrl: str
    bookSourceGroup: str = "default"
    enabled: bool = True


class LocalBookSourceImportRequest(BaseModel):
    file_path: str
    replace_existing: bool = True


@router.get("/book_sources")
async def list_book_sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    enabled_only: bool = False,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_service()
    result = await service.list_book_sources(page=page, page_size=page_size, enabled_only=enabled_only)
    return {
        "success": True,
        "code": "OK",
        "message": "book sources listed",
        "data": result["items"],
        "meta": result["meta"],
        "trace_id": None,
    }


@router.post("/book_sources")
async def create_book_source(
    payload: BookSourcePayload,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_service()
    item = await service.create_book_source(payload.model_dump(), identity.user_id)
    return {
        "success": True,
        "code": "OK",
        "message": "book source created",
        "data": item,
        "meta": {},
        "trace_id": None,
    }


@router.post("/book_sources/import")
async def import_book_sources(
    payload: LocalBookSourceImportRequest,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_service()
    data = await service.import_book_sources_from_file(
        payload.file_path,
        identity.user_id,
        replace_existing=payload.replace_existing,
    )
    return {
        "success": True,
        "code": "OK",
        "message": "book sources imported",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.get("/{source_type}/{source_id}/versions")
async def list_source_versions(
    source_type: str,
    source_id: str,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_runtime_service()
    data = await service.list_versions(source_type, source_id)
    return {
        "success": True,
        "code": "OK",
        "message": "source versions listed",
        "data": data,
        "meta": {"total": len(data)},
        "trace_id": None,
    }
