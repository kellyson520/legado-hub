"""UTC normalization for API boundaries and persisted legacy timestamps."""

from __future__ import annotations

from datetime import datetime, timezone


def ensure_utc(value: datetime | None) -> datetime | None:
    """Treat legacy naive values as UTC and normalize aware values to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_utc_iso(value: datetime | None) -> str | None:
    normalized = ensure_utc(value)
    if normalized is None:
        return None
    return normalized.isoformat().replace("+00:00", "Z")
