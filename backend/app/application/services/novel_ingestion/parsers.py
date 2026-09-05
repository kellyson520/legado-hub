from __future__ import annotations

import hashlib
import mimetypes
import posixpath
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath
from typing import Iterable
from zipfile import BadZipFile, ZipFile

from bs4 import BeautifulSoup, Comment


class NovelImportError(ValueError):
    code = "novel_import_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code


class UnsupportedNovelFormat(NovelImportError):
    code = "unsupported_format"


class InvalidNovelSplitMode(NovelImportError):
    code = "invalid_split_mode"


class UnsafeNovelArchive(NovelImportError):
    code = "unsafe_archive"


class EmptyNovelDocument(NovelImportError):
    code = "empty_document"


@dataclass(frozen=True)
class ParsedChapter:
    ordinal: int
    title: str
    text: str
    content_hash: str


@dataclass(frozen=True)
class ParsedNovelDocument:
    title: str
    author: str
    normalized_text: str
    chapters: list[ParsedChapter] = field(default_factory=list)
    content_hash: str = ""
    media_type: str = "text/plain"


class NovelDocumentParser:
    """Parse only bounded, text-oriented novel formats."""

    MAX_UNCOMPRESSED_EPUB_BYTES = 64 * 1024 * 1024
    MAX_EPUB_FILES = 2048

    _CHAPTER_RE = re.compile(
        r"^\s*(?:(?:第\s*[0-9一二三四五六七八九十百千万零两〇]+\s*章)|"
        r"(?:chapter|ch\.?)[\s_-]*\d+|序章|楔子|引子|番外|后记|尾声)\s*(.*)$",
        re.IGNORECASE,
    )

    _MEDIA_EXTENSIONS = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".html": "text/html",
        ".htm": "text/html",
        ".xhtml": "application/xhtml+xml",
        ".epub": "application/epub+zip",
    }

    def parse(
        self,
        filename: str,
        media_type: str | None,
        data: bytes,
        *,
        split_mode: str = "heading",
        fixed_size: int = 2000,
    ) -> ParsedNovelDocument:
        if not data:
            raise EmptyNovelDocument("novel document is empty")
        extension = self._extension(filename)
        normalized_media = (media_type or "").split(";", 1)[0].lower().strip()
        kind = self._kind(extension, normalized_media)
        if kind is None:
            raise UnsupportedNovelFormat(
                f"unsupported novel format: {filename or normalized_media}"
            )
        if kind == "epub":
            return self._parse_epub(filename, data)
        if kind == "html":
            text, title = self._html_to_text(data)
        else:
            text, title = self._decode(data), ""
        normalized = self._normalize_text(text)
        if not normalized:
            raise EmptyNovelDocument("novel document has no readable text")
        chapters = self._split_chapters(normalized, title=title, filename=filename, split_mode=split_mode, fixed_size=fixed_size)
        return self._document(filename, normalized, chapters, normalized_media or self._MEDIA_EXTENSIONS[extension], title)

    @classmethod
    def safe_extension(cls, filename: str, media_type: str | None = None) -> str:
        extension = cls._extension(filename)
        if extension in cls._MEDIA_EXTENSIONS:
            return extension
        media = (media_type or "").split(";", 1)[0].lower().strip()
        for candidate, candidate_media in cls._MEDIA_EXTENSIONS.items():
            if media == candidate_media:
                return candidate
        raise UnsupportedNovelFormat("unsupported novel file extension")

    @classmethod
    def _extension(cls, filename: str) -> str:
        name = (filename or "").lower().split("?", 1)[0]
        dot = name.rsplit("/", 1)[-1].rfind(".")
        return name[dot:] if dot >= 0 else ""

    @classmethod
    def _kind(cls, extension: str, media_type: str) -> str | None:
        if extension == ".epub" or media_type == "application/epub+zip":
            return "epub"
        if extension in {".html", ".htm", ".xhtml"} or media_type in {
            "text/html", "application/xhtml+xml"
        }:
            return "html"
        if extension in {".md", ".markdown"} or media_type in {
            "text/markdown", "text/x-markdown"
        }:
            return "markdown"
        if extension == ".txt" or media_type in {"text/plain", "text/x-fictionbook"}:
            return "text"
        return None

    @staticmethod
    def _decode(data: bytes) -> str:
        for encoding in ("utf-8-sig", "gb18030", "utf-16"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = []
        for raw_line in text.split("\n"):
            line = re.sub(r"[ \t\u3000]+", " ", raw_line).strip()
            lines.append(line)
        normalized = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
        return normalized.strip()

    def _html_to_text(self, data: bytes) -> tuple[str, str]:
        soup = BeautifulSoup(self._decode(data), "lxml")
        for node in soup.find_all(["script", "style", "noscript", "template"]):
            node.decompose()
        for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
            comment.extract()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        lines: list[str] = []
        for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "div", "br", "li"]):
            value = element.get_text(" ", strip=True)
            if value:
                lines.append(value)
        return "\n".join(lines) or soup.get_text("\n"), title

    def _parse_epub(self, filename: str, data: bytes) -> ParsedNovelDocument:
        try:
            archive = ZipFile(BytesIO(data))
        except BadZipFile as exc:
            raise UnsafeNovelArchive("invalid EPUB archive") from exc
        with archive:
            entries = archive.infolist()
            if len(entries) > self.MAX_EPUB_FILES:
                raise UnsafeNovelArchive("EPUB contains too many files")
            total_size = 0
            documents: list[tuple[str, str, str]] = []
            for info in entries:
                self._validate_archive_entry(info)
                total_size += info.file_size
                if total_size > self.MAX_UNCOMPRESSED_EPUB_BYTES:
                    raise UnsafeNovelArchive("EPUB uncompressed size exceeds limit")
                if info.is_dir() or not info.filename.lower().endswith((".xhtml", ".html", ".htm")):
                    continue
                raw = archive.read(info)
                text, title = self._html_to_text(raw)
                normalized = self._normalize_text(text)
                if normalized:
                    documents.append((info.filename, normalized, title))
        if not documents:
            raise EmptyNovelDocument("EPUB has no readable chapters")
        chapters: list[ParsedChapter] = []
        for index, (entry_name, text, title) in enumerate(sorted(documents), start=1):
            nested = self._split_chapters(text, title=title, filename=entry_name)
            if len(nested) == 1 and not nested[0].title:
                nested[0] = ParsedChapter(index, title or PurePosixPath(entry_name).stem, nested[0].text, nested[0].content_hash)
            for item in nested:
                chapters.append(ParsedChapter(len(chapters) + 1, item.title, item.text, item.content_hash))
        normalized = "\n\n".join(item.text for item in chapters if item.text)
        return self._document(filename, normalized, chapters, "application/epub+zip", "")

    @classmethod
    def _validate_archive_entry(cls, info) -> None:
        name = info.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise UnsafeNovelArchive(f"unsafe EPUB path: {info.filename}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise UnsafeNovelArchive(f"symlink entries are not allowed: {info.filename}")

    def _split_chapters(
        self,
        normalized: str,
        *,
        title: str,
        filename: str,
        split_mode: str = "heading",
        fixed_size: int = 2000,
    ) -> list[ParsedChapter]:
        if split_mode == "blank-line":
            chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", normalized) if chunk.strip()]
            return [ParsedChapter(index, f"{title or PurePosixPath(filename or '正文').stem} {index}", chunk, _hash(chunk)) for index, chunk in enumerate(chunks, start=1)]
        if split_mode == "fixed-size":
            if fixed_size < 1:
                raise NovelImportError("fixed_size must be positive", code="invalid_fixed_size")
            chunks = [normalized[index:index + fixed_size] for index in range(0, len(normalized), fixed_size)]
            return [ParsedChapter(index, f"{title or PurePosixPath(filename or '正文').stem} {index}", chunk, _hash(chunk)) for index, chunk in enumerate(chunks, start=1)]
        if split_mode != "heading":
            raise InvalidNovelSplitMode(f"unsupported split mode: {split_mode}")
        lines = normalized.split("\n")
        markers: list[tuple[int, str]] = []
        for index, line in enumerate(lines):
            heading = line.lstrip("# ").strip() if line.lstrip().startswith("#") else line
            if self._CHAPTER_RE.match(heading) or (line.lstrip().startswith("#") and heading):
                markers.append((index, heading))
        if not markers:
            chapter_title = title or PurePosixPath(filename or "正文").stem or "正文"
            return [ParsedChapter(1, chapter_title, normalized, _hash(normalized))]
        chapters: list[ParsedChapter] = []
        for marker_index, (line_index, heading) in enumerate(markers):
            end = markers[marker_index + 1][0] if marker_index + 1 < len(markers) else len(lines)
            text = self._normalize_text("\n".join(lines[line_index + 1:end]))
            if not text:
                continue
            chapters.append(ParsedChapter(len(chapters) + 1, heading, text, _hash(text)))
        if not chapters:
            raise EmptyNovelDocument("novel document has no chapter text")
        return chapters

    @staticmethod
    def _document(filename: str, normalized: str, chapters: list[ParsedChapter], media_type: str, title: str):
        return ParsedNovelDocument(
            title=title or PurePosixPath(filename or "小说").stem,
            author="",
            normalized_text=normalized,
            chapters=chapters,
            content_hash=_hash(normalized),
            media_type=media_type,
        )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
