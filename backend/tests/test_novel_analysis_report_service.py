from app.application.services.novel_code_report_service import NovelCodeReportService


class Work:
    id = "work-1"


class Chapter:
    def __init__(self, chapter_id, index, title):
        self.id = chapter_id
        self.chapter_index = index
        self.title = title


class Variant:
    def __init__(self, content, verified=True):
        self.content = content
        self.is_verified = verified


class Repo:
    def get_work(self, work_id):
        return Work() if work_id == "work-1" else None

    def list_canonical_chapters(self, work_id):
        return [Chapter("c1", 1, "第一章"), Chapter("c2", 2, "第二章")]

    def list_content_variants(self, chapter_id):
        return [Variant("林默在子时进入长安。" if chapter_id == "c1" else "苏晚与林默重逢。")]


def test_code_report_service_returns_bounded_deterministic_report():
    response = NovelCodeReportService(Repo()).build("work-1", chapter_limit=1)
    assert response["work_id"] == "work-1"
    assert response["chapter_count"] == 1
    assert response["report"]["chapters"]
    assert response["report"]["time_mentions"]
