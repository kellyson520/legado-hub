"""Compatibility facade for the pre-DDD database import path.

New code must import SQLite primitives from the persistence infrastructure.
This module remains intentionally tiny so old integrations keep working while
the ownership of database concerns stays in one place.
"""

from app.infrastructure.persistence.sqlite.session import Base, SessionLocal, engine, get_db

__all__ = ["Base", "SessionLocal", "engine", "get_db"]
