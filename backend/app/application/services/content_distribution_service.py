from app.core.exceptions import NotFoundException


class ContentDistributionService:
    def __init__(self, repo):
        self._repo = repo

    def list_works(self, *, tenant_id: str) -> list[dict]:
        return [
            {
                'id': work.id,
                'title': work.title,
                'author': work.author,
            }
            for work in self._repo.list_works()
        ]

    def get_work(self, *, tenant_id: str, work_id: str) -> dict:
        work = self._repo.get_work(work_id)
        if work is None:
            raise NotFoundException('Work not found')
        return {'id': work.id, 'title': work.title, 'author': work.author}

    def get_toc(self, *, tenant_id: str, work_id: str) -> list[dict]:
        work = self._repo.get_work(work_id)
        if work is None:
            raise NotFoundException('Work not found')
        return [
            {
                'id': chapter.id,
                'chapter_index': chapter.chapter_index,
                'title': chapter.title,
            }
            for chapter in self._repo.list_canonical_chapters(work_id)
        ]

    def read_chapter(self, *, tenant_id: str, chapter_id: str) -> dict:
        chapter = self._repo.get_canonical_chapter(chapter_id)
        if chapter is None:
            raise NotFoundException('Chapter not found')
        variants = sorted(self._repo.list_content_variants(chapter_id), key=self._variant_sort_key, reverse=True)
        fallback_count = 0
        selected = None
        for variant in variants:
            if variant.content:
                selected = variant
                break
            fallback_count += 1
        if selected is None:
            raise NotFoundException('Chapter content not found')

        route_summary = {
            'selected_source_id': selected.source_id,
            'fallback_count': fallback_count,
            'candidate_count': len(variants),
        }
        self._repo.record_route_decision(
            tenant_id=tenant_id,
            canonical_chapter_id=chapter_id,
            selected_variant_id=selected.id,
            fallback_count=fallback_count,
            route_summary=route_summary,
        )
        return {
            'result': {
                'chapter_id': chapter.id,
                'title': chapter.title,
                'source_id': selected.source_id,
                'content': selected.content,
                'variant_id': selected.id,
            },
            'route_summary': route_summary,
        }

    @staticmethod
    def _variant_sort_key(variant) -> tuple:
        health_rank = {
            'healthy': 3,
            'degraded': 2,
            'unknown': 1,
            'blocked': 0,
        }.get(variant.health_status, 1)
        return (
            health_rank,
            1 if variant.is_verified else 0,
            float(variant.quality_score),
            float(variant.coverage_score),
            float(variant.freshness_score),
            -int(variant.latency_ms),
        )
