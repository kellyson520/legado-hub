import hashlib
import unicodedata
from uuid import uuid4

from app.domain.entities.evidence import EvidenceSpan


_SENTENCE_BOUNDARIES = frozenset("。！？!?；;…\n")


class EvidenceService:
    def __init__(self, repo, canonical_repo):
        self._repo = repo
        self._canonical_repo = canonical_repo

    def create_spans(
        self,
        *,
        content_variant_id: str,
        canonical_chapter_id: str,
        content: str,
        max_chars: int,
    ) -> list[EvidenceSpan]:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        normalized_content = self._normalize_content(content)
        content_sha256 = self._sha256(normalized_content)
        spans = [
            EvidenceSpan(
                id=uuid4().hex,
                canonical_chapter_id=canonical_chapter_id,
                content_variant_id=content_variant_id,
                start_offset=start_offset,
                end_offset=end_offset,
                excerpt=excerpt,
                excerpt_sha256=self._sha256(excerpt),
                content_sha256=content_sha256,
            )
            for start_offset, end_offset, excerpt in self._split(normalized_content, max_chars)
        ]
        return self._repo.create_spans(spans)

    def get_verified_span(self, span_id: str) -> EvidenceSpan | None:
        span = self._repo.get_span(span_id)
        if span is None:
            return None
        variant = self._canonical_repo.get_content_variant(span.content_variant_id)
        if variant is None:
            return None
        current_content_hash = self._sha256(self._normalize_content(variant.content))
        return span if current_content_hash == span.content_sha256 else None

    @staticmethod
    def _normalize_content(content: str) -> str:
        return unicodedata.normalize("NFC", (content or "").replace("\r\n", "\n").replace("\r", "\n"))

    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _split(content: str, max_chars: int):
        start_offset = 0
        while start_offset < len(content):
            hard_end = min(start_offset + max_chars, len(content))
            end_offset = hard_end
            if hard_end < len(content):
                candidate = content[start_offset:hard_end]
                boundary = max(
                    (index for index, char in enumerate(candidate) if char in _SENTENCE_BOUNDARIES),
                    default=-1,
                )
                if boundary >= 0:
                    end_offset = start_offset + boundary + 1
            if end_offset <= start_offset:
                end_offset = hard_end
            yield start_offset, end_offset, content[start_offset:end_offset]
            start_offset = end_offset
