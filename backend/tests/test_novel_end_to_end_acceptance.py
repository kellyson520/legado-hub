from app.application.services.novel_code_report_service import NovelCodeReportService
from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService
from app.application.services.novel_analysis_pipeline_service import select_analysis_evidence
from app.application.services.novel_ingestion.parsers import NovelDocumentParser


class Variant:
    def __init__(self, content):
        self.content = content
        self.is_verified = True


class Work:
    id = "work-e2e"


class Repo:
    def __init__(self, chapters):
        self.chapters = chapters

    def get_work(self, work_id):
        return Work() if work_id == "work-e2e" else None

    def list_canonical_chapters(self, work_id):
        return [type("Chapter", (), chapter) for chapter in self.chapters]

    def list_content_variants(self, chapter_id):
        return [Variant(next(ch["content"] for ch in self.chapters if ch["id"] == chapter_id))]


def test_txt_to_chapter_report_acceptance_without_llm():
    document = NovelDocumentParser().parse(
        "星河纪事.txt",
        "text/plain",
        "第一章 雨夜\n林默在子时进入长安。\n\n第二章 重逢\n三天后，林默与苏晚重逢。".encode(),
    )
    chapters = [
        {"id": f"c{item.ordinal}", "chapter_index": item.ordinal, "title": item.title, "content": item.text}
        for item in document.chapters
    ]
    report = NovelCodeReportService(Repo(chapters)).build("work-e2e", chapter_limit=10)
    data = report["report"]
    assert report["chapter_count"] == 2
    assert document.content_hash
    assert data["content_sha256"]
    cached = NovelCodeReportService(Repo(chapters)).build("work-e2e", chapter_limit=10)
    assert cached["report"]["content_sha256"] == data["content_sha256"]
    assert cached["report"]["cache_hit"] is True
    assert "林默" in [item["name"] for item in data["characters"]]
    assert any(item["normalized"] == "子时" for item in data["time_mentions"])
    assert any(item["normalized"] == "三天后" and item["anchor_status"] == "unresolved" for item in data["time_mentions"])
    assert all(item["evidence"] for item in data["events"] + data["time_mentions"])
    raw_report = NovelCodeAnalysisService().analyze(
        "work-e2e",
        [{"chapter_id": item["id"], "chapter_index": item["chapter_index"], "title": item["title"], "content": item["content"]} for item in chapters],
    )
    selected = select_analysis_evidence(raw_report, max_chapters=1, max_spans=2)
    assert len(selected) <= 2
