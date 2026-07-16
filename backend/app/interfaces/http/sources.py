from fastapi import APIRouter, Body, Depends, Query
from typing import Any

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


@router.post("/import")
async def import_legado_json_sources(
    payload: Any = Body(...),
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    data = await build_source_runtime_service().import_legado_sources(payload, str(identity.user_id))
    return {"success": True, "code": "OK", "message": "Legado 书源导入完成", "data": data, "meta": {}, "trace_id": None}


@router.get("/export")
async def export_legado_json_sources(
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    data = await build_source_runtime_service().export_legado_sources(str(identity.user_id))
    return {"success": True, "code": "OK", "message": "Legado 书源导出完成", "data": data, "meta": {"total": len(data)}, "trace_id": None}


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


@router.get("/visible")
async def list_visible_source_versions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    result = await build_source_runtime_service().list_visible_sources(
        str(identity.user_id),
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "code": "OK",
        "message": "visible source inventory listed",
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


@router.get("/versions/{source_version_id}")
async def get_source_rule_version(
    source_version_id: str,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    data = await build_source_runtime_service().get_version_detail(source_version_id)
    return {
        "success": True,
        "code": "OK",
        "message": "书源规则版本已加载",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.post("/versions/{source_version_id}/drafts")
async def create_source_rule_draft(
    source_version_id: str,
    payload: dict = Body(...),
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    data = await build_source_runtime_service().create_rule_draft(source_version_id, payload, str(identity.user_id))
    return {
        "success": True,
        "code": "OK",
        "message": "书源规则候选版本已保存",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.post("/versions/{source_version_id}/validate")
async def validate_source_rule_version(
    source_version_id: str,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    service = build_source_runtime_service()
    try:
        data = await service.validate_rule_version(source_version_id, str(identity.user_id))
    finally:
        await service.aclose()
    return {
        "success": True,
        "code": "OK",
        "message": "书源规则验证完成",
        "data": data,
        "meta": {},
        "trace_id": None,
    }


@router.post("/versions/{source_version_id}/publish")
async def publish_source_rule_version(
    source_version_id: str,
    identity: RequestIdentity = Depends(get_current_identity),
    _=Depends(require_permission(Permission.BOOK_SOURCES_WRITE)),
):
    data = await build_source_runtime_service().publish_rule_version(source_version_id, str(identity.user_id))
    return {
        "success": True,
        "code": "OK",
        "message": "书源规则版本已发布",
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
