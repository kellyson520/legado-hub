from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .source_repo_impl import SQLiteSourceRepository

__all__ = [
    "SQLiteSourceRepository",
]


def __getattr__(name):
    if name == "SQLiteSourceRepository":
        from .source_repo_impl import SQLiteSourceRepository
        return SQLiteSourceRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
