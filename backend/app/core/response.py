"""
统一 API 响应格式
- 所有模块对外输出必须遵循此格式
- 支持分页、元数据、追踪 ID 透传
- 与异常体系联动，确保一致性

标准响应格式:
{
    "success": bool,
    "code": string,      # 业务状态码，如 "OK", "NOT_FOUND"
    "message": string,
    "data": any,
    "meta": {},          # 分页、统计等元信息
    "trace_id": string   # 用于链路追踪
}
"""

from collections.abc import Mapping
from typing import Any, Optional, Dict, TypeVar, Generic
from pydantic import BaseModel, Field
from pydantic.generics import GenericModel
from .logging import get_trace_id
from .pagination import pagination_meta

T = TypeVar("T")


class ApiMeta(BaseModel):
    """响应元数据"""
    page: Optional[int] = None
    page_size: Optional[int] = None
    total: Optional[int] = None
    total_pages: Optional[int] = None
    
    class Config:
        extra = "allow"


class UnifiedResponse(GenericModel, Generic[T]):
    """
    统一 API 响应模型
    
    所有接口返回的数据必须包装为此结构。
    """
    success: bool = Field(default=True, description="是否成功")
    code: str = Field(default="OK", description="业务状态码")
    message: str = Field(default="success", description="人类可读消息")
    data: Optional[T] = Field(default=None, description="业务数据")
    meta: Optional[ApiMeta] = Field(default=None, description="元数据（分页等）")
    trace_id: Optional[str] = Field(default=None, description="链路追踪 ID")
    
    class Config:
        extra = "allow"


# ==================== 便捷构造函数 ====================

def ok(data: Any = None, message: str = "success", meta: Optional[Dict] = None) -> Dict:
    """构造成功响应"""
    resp = {
        "success": True,
        "code": "OK",
        "message": message,
        "data": data,
        "trace_id": get_trace_id(),
    }
    if meta:
        resp["meta"] = meta
    return resp


def created(data: Any = None, message: str = "创建成功") -> Dict:
    """构造创建成功响应"""
    return {
        "success": True,
        "code": "CREATED",
        "message": message,
        "data": data,
        "trace_id": get_trace_id(),
    }


def paginated(
    items: list,
    total: int,
    page: int,
    page_size: int,
    message: str = "success"
) -> Dict:
    """构造分页响应"""
    return {
        "success": True,
        "code": "OK",
        "message": message,
        "data": items,
        "meta": pagination_meta(page, page_size, total),
        "trace_id": get_trace_id(),
    }


def from_paginated_result(result: Mapping[str, Any], message: str = "success") -> Dict:
    """Adapt a service ``items/meta`` result to the public API envelope."""
    return ok(
        data=result["items"],
        message=message,
        meta=result["meta"],
    )


def fail(
    message: str = "操作失败",
    code: str = "ERROR",
    data: Any = None,
    details: Optional[Dict] = None
) -> Dict:
    """构造失败响应（用于非异常场景的业务失败）"""
    resp = {
        "success": False,
        "code": code,
        "message": message,
        "data": data,
        "trace_id": get_trace_id(),
    }
    if details:
        resp["details"] = details
    return resp


def from_exception(exc) -> Dict:
    """从异常构造响应"""
    return {
        "success": False,
        "code": getattr(exc, "code", getattr(exc, "error_code", "INTERNAL_ERROR")),
        "message": getattr(exc, "message", str(exc)),
        "data": None,
        "trace_id": get_trace_id(),
    }
