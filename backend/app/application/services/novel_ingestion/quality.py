from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NovelImportWarning:
    code: str
    message: str
    chapter_index: int | None = None


@dataclass(frozen=True)
class NovelImportPreview:
    content_hash: str
    title: str
    author: str
    media_type: str
    total_chars: int
    chapters: list[dict[str, Any]]
    warnings: list[NovelImportWarning]


def build_import_preview(
    document,
    *,
    max_chapters: int = 5000,
    min_chapter_chars: int = 20,
    preview_chars: int = 120,
) -> NovelImportPreview:
    source_chapters = list(getattr(document, "chapters", ()) or ())
    warnings: list[NovelImportWarning] = []
    if len(source_chapters) > max_chapters:
        warnings.append(
            NovelImportWarning(
                code="too_many_chapters",
                message=f"document contains {len(source_chapters)} chapters; preview is limited to {max_chapters}",
            )
        )
    chapters = []
    for index, chapter in enumerate(source_chapters[:max_chapters], start=1):
        text = str(getattr(chapter, "text", "") or "").strip()
        title = str(getattr(chapter, "title", "") or "").strip()
        item = {
            "ordinal": int(getattr(chapter, "ordinal", index) or index),
            "title": title,
            "word_count": len(text),
            "content_hash": str(getattr(chapter, "content_hash", "") or ""),
            "preview": text[:max(0, preview_chars)],
        }
        chapters.append(item)
        if len(text) < min_chapter_chars:
            warnings.append(
                NovelImportWarning(
                    code="short_chapter",
                    message=f"chapter {index} contains only {len(text)} characters",
                    chapter_index=index,
                )
            )

    document_title = str(getattr(document, "title", "") or "").strip()
    if len(source_chapters) == 1:
        chapter_title = chapters[0]["title"] if chapters else ""
        if not chapter_title or chapter_title == document_title:
            warnings.append(
                NovelImportWarning(
                    code="no_heading_detected",
                    message="no chapter heading was detected; the document is represented as one chapter",
                )
            )

    return NovelImportPreview(
        content_hash=str(getattr(document, "content_hash", "") or ""),
        title=document_title,
        author=str(getattr(document, "author", "") or "").strip(),
        media_type=str(getattr(document, "media_type", "text/plain") or "text/plain"),
        total_chars=len(str(getattr(document, "normalized_text", "") or "")),
        chapters=chapters,
        warnings=warnings,
    )
