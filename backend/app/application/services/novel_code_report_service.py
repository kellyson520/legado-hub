from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService


class NovelCodeReportService:
    def __init__(self, canonical_repo, analyzer=None):
        self._canonical_repo = canonical_repo
        self._analyzer = analyzer or NovelCodeAnalysisService()

    def build(self, work_id: str, *, chapter_limit: int = 8) -> dict:
        work = self._canonical_repo.get_work(work_id)
        if work is None:
            raise LookupError("work not found")
        limit = max(1, min(int(chapter_limit), 24))
        chapters = []
        for chapter in self._canonical_repo.list_canonical_chapters(work_id)[:limit]:
            variants = [item for item in self._canonical_repo.list_content_variants(chapter.id) if item.is_verified and item.content]
            if not variants:
                continue
            chapters.append({
                "chapter_id": chapter.id,
                "chapter_index": chapter.chapter_index,
                "title": chapter.title,
                "content": variants[0].content,
            })
        report = self._analyzer.analyze(work_id, chapters)
        return {
            "work_id": work_id,
            "chapter_count": len(chapters),
            "report": report.to_dict(),
        }
