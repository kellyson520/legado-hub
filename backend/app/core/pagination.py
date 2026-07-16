"""Shared pagination and SQL search helpers for list endpoints."""

from math import ceil
from typing import Any


def pagination_meta(
    page: int,
    page_size: int,
    total: int,
    **extra: Any,
) -> dict[str, Any]:
    """Build the canonical pagination metadata mapping.

    ``None`` extras are omitted so optional filters do not leak into the
    response contract, while empty strings remain visible as submitted search
    values.
    """
    safe_total = max(int(total), 0)
    total_pages = ceil(safe_total / page_size) if page_size > 0 and safe_total else 0
    metadata: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "total": safe_total,
        "total_pages": total_pages,
    }
    metadata.update({key: value for key, value in extra.items() if value is not None})
    return metadata


def like_pattern(value: str) -> str:
    """Create a SQL LIKE/ILIKE pattern for a literal user search string.

    Callers must pass ``escape="\\"`` to SQLAlchemy's ``like``/``ilike``
    operator when using this pattern.
    """
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
