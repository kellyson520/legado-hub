from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.permissions import Permission
from app.infrastructure.persistence.factory import (
    build_character_calibration_service,
    build_source_complement_service,
    build_source_read_service,
)
from app.interfaces.http.deps import require_permission


router = APIRouter()


class ReadingSearchRequest(BaseModel):
    keyword: str
    source_ids: list[int] | None = None
    limit_per_source: int = 3
    author_hint: str | None = None
    routing_mode: str = "auto"
    include_health: bool = False


class ReadingTocRequest(BaseModel):
    source_id: int
    book_url: str
    book_name: str | None = None
    author_hint: str | None = None
    routing_mode: str = "auto"


class ReadingContentRequest(BaseModel):
    source_id: int
    chapter_url: str
    book_name: str | None = None
    author_hint: str | None = None
    chapter_title: str | None = None
    chapter_index: int | None = None
    routing_mode: str = "auto"


class ReadingComplementItem(BaseModel):
    source_id: int
    chapter_url: str
    source_name: str | None = None
    source_url: str | None = None


class ReadingComplementRequest(BaseModel):
    book_name: str
    chapter_title: str
    chapter_num: int
    items: list[ReadingComplementItem]
    reference_content: str = ""
    merge_strategy: str = "hybrid"


class ReadingCharacterCalibrationItem(BaseModel):
    source_id: int | None = None
    name: str = ""
    author: str = ""
    excerpt: str = ""


class ReadingCharacterCalibrationRequest(BaseModel):
    keyword: str
    items: list[ReadingCharacterCalibrationItem]


@router.post("/search")
async def search_books(
    payload: ReadingSearchRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_read_service()
    data = await service.search_books(
        payload.keyword,
        payload.source_ids,
        payload.limit_per_source,
        payload.author_hint,
        payload.routing_mode,
        payload.include_health,
    )
    return {
        "success": True,
        "code": "OK",
        "message": "search completed",
        "data": data["items"],
        "meta": data["route_summary"],
        "trace_id": None,
    }


@router.post("/toc")
async def get_book_toc(
    payload: ReadingTocRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_read_service()
    data = await service.get_book_toc(
        payload.source_id,
        payload.book_url,
        payload.book_name,
        payload.author_hint,
        payload.routing_mode,
    )
    return {
        "success": True,
        "code": "OK",
        "message": "toc loaded",
        "data": data,
        "meta": {
            "total": len(data["chapters"]),
            "resolved_source_id": data["resolved_source_id"],
            "fallback_used": data["fallback_used"],
        },
        "trace_id": None,
    }


@router.post("/content")
async def get_chapter_content(
    payload: ReadingContentRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_read_service()
    data = await service.get_chapter_content(
        payload.source_id,
        payload.chapter_url,
        payload.book_name,
        payload.author_hint,
        payload.chapter_title,
        payload.chapter_index,
        payload.routing_mode,
    )
    return {
        "success": True,
        "code": "OK",
        "message": "content loaded",
        "data": data,
        "meta": {
            "resolved_source_id": data["resolved_source_id"],
            "fallback_used": data["fallback_used"],
        },
        "trace_id": None,
    }


@router.post("/complement")
async def complement_chapter(
    payload: ReadingComplementRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_source_complement_service()
    try:
        data = await service.complement_chapter_candidates(
            book_name=payload.book_name,
            chapter_title=payload.chapter_title,
            chapter_num=payload.chapter_num,
            items=[item.model_dump() for item in payload.items],
            reference_content=payload.reference_content,
            merge_strategy=payload.merge_strategy,
        )
    finally:
        await service.aclose()

    return {
        "success": True,
        "code": "OK",
        "message": "complement completed",
        "data": data,
        "meta": {
            "successful_sources": data["successful_sources"],
            "failed_sources": data["failed_sources"],
        },
        "trace_id": None,
    }


@router.post("/characters/calibrate")
async def calibrate_characters(
    payload: ReadingCharacterCalibrationRequest,
    _=Depends(require_permission(Permission.BOOK_SOURCES_READ)),
):
    service = build_character_calibration_service()
    data = await service.calibrate(
        keyword=payload.keyword,
        items=[item.model_dump() for item in payload.items],
    )
    return {
        "success": True,
        "code": "OK",
        "message": "character calibration completed",
        "data": data,
        "meta": {"pairwise": len(data["pairwise"])},
        "trace_id": None,
    }
