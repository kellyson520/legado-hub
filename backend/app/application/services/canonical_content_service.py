import re
from difflib import SequenceMatcher

from app.domain.entities.canonical_content import (
    AlignmentResult,
    CanonicalChapter,
    CanonicalWork,
    ChapterMatch,
    ContentVariant,
    SourceChapter,
    SourceWork,
)


def normalize_text(value: str) -> str:
    lowered = re.sub(r'\s+', ' ', (value or '').strip().lower())
    return re.sub(r'[^0-9a-z\u4e00-\u9fff ]+', '', lowered)


def extract_chapter_number(value: str) -> int | None:
    match = re.search(r'(\d+)', value or '')
    return int(match.group(1)) if match else None


class CanonicalContentService:
    def __init__(self, repo):
        self._repo = repo

    def create_canonical_work(self, *, title: str, author: str) -> CanonicalWork:
        work = self._repo.create_canonical_work(title=title, author=author)
        self._repo.add_alias(work.id, alias=title, alias_type='title')
        return work

    def add_canonical_chapters(self, canonical_work_id: str, titles: list[str]) -> list[CanonicalChapter]:
        return [
            self._repo.add_canonical_chapter(canonical_work_id=canonical_work_id, chapter_index=index, title=title)
            for index, title in enumerate(titles)
        ]

    def create_source_work(
        self,
        canonical_work_id: str,
        *,
        source_id: str,
        title: str,
        author: str,
    ) -> SourceWork:
        return self._repo.create_source_work(
            canonical_work_id=canonical_work_id,
            source_id=source_id,
            title=title,
            author=author,
        )

    def add_source_chapter(
        self,
        source_work_id: str,
        *,
        title: str,
        chapter_url: str,
        chapter_index: int,
        canonical_chapter_id: str | None = None,
    ) -> SourceChapter:
        return self._repo.add_source_chapter(
            source_work_id=source_work_id,
            chapter_index=chapter_index,
            title=title,
            chapter_url=chapter_url,
            canonical_chapter_id=canonical_chapter_id,
        )

    def save_alignment(
        self,
        *,
        canonical_chapter_id: str,
        source_chapter_id: str,
        confidence: float,
        evidence: dict,
        review_status: str,
    ):
        return self._repo.save_alignment(
            canonical_chapter_id=canonical_chapter_id,
            source_chapter_id=source_chapter_id,
            confidence=confidence,
            evidence=evidence,
            review_status=review_status,
        )

    def add_content_variant(
        self,
        *,
        canonical_chapter_id: str,
        source_chapter_id: str,
        source_id: str,
        content: str,
        health_status: str = 'unknown',
        quality_score: float = 0.0,
        coverage_score: float = 0.0,
        freshness_score: float = 0.0,
        latency_ms: int = 0,
        is_verified: bool = True,
    ) -> ContentVariant:
        return self._repo.add_content_variant(
            canonical_chapter_id=canonical_chapter_id,
            source_chapter_id=source_chapter_id,
            source_id=source_id,
            content=content,
            health_status=health_status,
            quality_score=quality_score,
            coverage_score=coverage_score,
            freshness_score=freshness_score,
            latency_ms=latency_ms,
            is_verified=is_verified,
        )

    def align_chapters(self, canonical: list[str], source: list[str]) -> AlignmentResult:
        matches: list[ChapterMatch] = []
        review_items: list[dict] = []
        for source_index, source_title in enumerate(source):
            best_index = 0
            best_score = -1.0
            for canonical_index, canonical_title in enumerate(canonical):
                score = self._score_alignment(
                    canonical_title=canonical_title,
                    source_title=source_title,
                    canonical_index=canonical_index,
                    source_index=source_index,
                    canonical_count=len(canonical),
                    source_count=len(source),
                )
                if score > best_score:
                    best_score = score
                    best_index = canonical_index
            review_status = 'accepted' if best_score >= 0.6 else 'review'
            match = ChapterMatch(
                canonical_index=best_index,
                source_index=source_index,
                confidence=round(best_score, 4),
                canonical_title=canonical[best_index],
                source_title=source_title,
                review_status=review_status,
            )
            matches.append(match)
            if review_status == 'review':
                review_items.append(
                    {
                        'canonical_index': best_index,
                        'canonical_title': canonical[best_index],
                        'source_index': source_index,
                        'source_title': source_title,
                        'confidence': round(best_score, 4),
                    }
                )
        return AlignmentResult(matches=matches, review_items=review_items)

    def ingest_source_chapters(
        self,
        *,
        canonical_work_id: str,
        source_id: str,
        title: str,
        author: str,
        chapters: list[dict],
    ) -> AlignmentResult:
        source_work = self.create_source_work(
            canonical_work_id,
            source_id=source_id,
            title=title,
            author=author,
        )
        canonical_chapters = self._repo.list_canonical_chapters(canonical_work_id)
        result = self.align_chapters(
            canonical=[chapter.title for chapter in canonical_chapters],
            source=[chapter.get('title', '') for chapter in chapters],
        )

        for match, chapter in zip(result.matches, chapters, strict=False):
            canonical_chapter = canonical_chapters[match.canonical_index]
            source_chapter = self.add_source_chapter(
                source_work.id,
                title=chapter.get('title', ''),
                chapter_url=chapter.get('chapter_url', ''),
                chapter_index=match.source_index,
                canonical_chapter_id=canonical_chapter.id,
            )
            alignment = self.save_alignment(
                canonical_chapter_id=canonical_chapter.id,
                source_chapter_id=source_chapter.id,
                confidence=match.confidence,
                evidence={
                    'canonical_title': canonical_chapter.title,
                    'source_title': source_chapter.title,
                    'canonical_index': match.canonical_index,
                    'source_index': match.source_index,
                },
                review_status=match.review_status,
            )
            match.canonical_chapter_id = alignment.canonical_chapter_id
            match.source_chapter_id = alignment.source_chapter_id
        return result

    @staticmethod
    def _score_alignment(
        *,
        canonical_title: str,
        source_title: str,
        canonical_index: int,
        source_index: int,
        canonical_count: int,
        source_count: int,
    ) -> float:
        canonical_norm = normalize_text(canonical_title)
        source_norm = normalize_text(source_title)
        score = 0.0

        if canonical_index == source_index:
            score += 0.35
            if canonical_count == source_count:
                score += 0.05

        canonical_number = extract_chapter_number(canonical_title)
        source_number = extract_chapter_number(source_title)
        if canonical_number is not None and canonical_number == source_number:
            score += 0.36

        title_similarity = SequenceMatcher(None, canonical_norm, source_norm).ratio()
        score += title_similarity * 0.2

        canonical_tokens = set(canonical_norm.split())
        source_tokens = set(source_norm.split())
        if canonical_tokens and source_tokens:
            overlap = len(canonical_tokens & source_tokens) / len(canonical_tokens | source_tokens)
            score += overlap * 0.1

        return min(score, 1.0)
