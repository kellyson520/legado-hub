"""Compatibility facade for the source-domain rule engine.

The implementation belongs to ``domain.services``. This import path remains
available for older integrations while new code should depend on the domain
module directly.
"""

from app.domain.services.source_compatibility import (
    FALLBACK_RULES,
    SITE_COMPATIBILITY_RULES,
    CompatibilityEngine,
    compat_engine,
)

__all__ = [
    "SITE_COMPATIBILITY_RULES",
    "FALLBACK_RULES",
    "CompatibilityEngine",
    "compat_engine",
]
