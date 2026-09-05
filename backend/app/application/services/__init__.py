from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .source_service import SourceAppService
    from .auth_service import AuthAppService
    from .translation_service import TranslationAppService
    from .novel_app_service import NovelAppService

__all__ = [
    "SourceAppService",
    "AuthAppService",
    "TranslationAppService",
    "NovelAppService",
]


def __getattr__(name):
    if name == "SourceAppService":
        from .source_service import SourceAppService
        return SourceAppService
    if name == "AuthAppService":
        from .auth_service import AuthAppService
        return AuthAppService
    if name == "TranslationAppService":
        from .translation_service import TranslationAppService
        return TranslationAppService
    if name == "NovelAppService":
        from .novel_app_service import NovelAppService
        return NovelAppService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
