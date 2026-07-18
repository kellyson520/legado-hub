"""Ports for importing external Legado source definitions."""

from __future__ import annotations

from typing import Any, Protocol


class SourceImportParser(Protocol):
    """Parse a source document without exposing its transport implementation."""

    def parse_sources_from_text(
        self,
        text: str,
        origin: str = "",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return book-source and RSS-source payloads in that order."""
