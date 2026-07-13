from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .factory import RepositoryFactory, get_source_repo, get_user_repo, get_translation_repo

__all__ = ["RepositoryFactory", "get_source_repo", "get_user_repo", "get_translation_repo"]


def __getattr__(name):
    if name in ("RepositoryFactory", "get_source_repo", "get_user_repo", "get_translation_repo"):
        from .factory import RepositoryFactory, get_source_repo, get_user_repo, get_translation_repo
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")