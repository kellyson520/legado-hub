from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .source_repo_impl import SQLiteSourceRepository
    from .user_repo_impl import SQLiteUserRepository
    from .translation_repo_impl import SQLiteTranslationRepository
    from .novel_repo_impl import SqliteNovelRepository

__all__ = [
    "SQLiteSourceRepository",
    "SQLiteUserRepository",
    "SQLiteTranslationRepository",
    "SqliteNovelRepository",
]


def __getattr__(name):
    if name == "SQLiteSourceRepository":
        from .source_repo_impl import SQLiteSourceRepository
        return SQLiteSourceRepository
    if name == "SQLiteUserRepository":
        from .user_repo_impl import SQLiteUserRepository
        return SQLiteUserRepository
    if name == "SQLiteTranslationRepository":
        from .translation_repo_impl import SQLiteTranslationRepository
        return SQLiteTranslationRepository
    if name == "SqliteNovelRepository":
        from .novel_repo_impl import SqliteNovelRepository
        return SqliteNovelRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
