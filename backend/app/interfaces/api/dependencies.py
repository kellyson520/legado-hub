"""
接口层依赖注入

职责：
- 将应用层服务注入到路由中
- 导出核心认证依赖（供路由使用）
- 管理请求生命周期（trace_id 由 TraceMiddleware 统一管理）
"""

from fastapi import Depends

from ...core.dependencies import get_auth_context, AuthContext
from ...infrastructure.persistence.factory import get_source_repo, get_user_repo, get_translation_repo
from ...application.services import SourceAppService, AuthAppService, TranslationAppService


def get_source_service() -> SourceAppService:
    """注入源管理应用服务"""
    repo = get_source_repo()
    return SourceAppService(repo)


def get_auth_service() -> AuthAppService:
    """注入认证应用服务"""
    repo = get_user_repo()
    return AuthAppService(repo)


def get_translation_service() -> TranslationAppService:
    """注入翻译应用服务"""
    repo = get_translation_repo()
    return TranslationAppService(repo)
