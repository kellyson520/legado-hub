import json
from types import SimpleNamespace

import pytest


class TextProvider:
    def __init__(self, response="provider output"):
        self.response = response
        self.calls = []

    def complete(self, prompt=None, system=None):
        self.calls.append((prompt, system))
        return self.response


def _skill_config():
    from app.services.novel_agent.config import AgentConfig

    return AgentConfig(config_dict={"memory": {"enable_project_memory": False}})


def test_extractor_relation_patterns_are_all_valid_regexes():
    import re

    from app.services.novel_agent.skills.extractor import ExtractorSkill

    for patterns in ExtractorSkill.RELATION_PATTERNS.values():
        for pattern in patterns:
            re.compile(pattern)


def test_writer_uses_configured_provider_output():
    from app.services.novel_agent.skills.writer import WriterSkill
    from app.services.novel_agent.store import NovelDataStore

    provider = TextProvider("由模型生成的续写")
    result = WriterSkill(NovelDataStore(), config=_skill_config(), provider=provider).execute(
        "generate_continuation", prompt="继续", chapter_num=3, length=100
    )

    assert result["available"] is True
    assert result["mode"] == "provider"
    assert result["content"] == "由模型生成的续写"
    assert provider.calls


def test_writer_reports_provider_unavailable_instead_of_claiming_template_generation():
    from app.services.novel_agent.skills.writer import WriterSkill
    from app.services.novel_agent.store import NovelDataStore

    result = WriterSkill(NovelDataStore(), config=_skill_config()).execute(
        "generate_continuation", prompt="继续", chapter_num=3, length=100
    )

    assert result["available"] is False
    assert result["status"] == "unavailable"
    assert result["error_code"] == "provider_unavailable"


def test_reasoner_prediction_uses_provider_output_when_configured():
    from app.services.novel_agent.skills.reasoner import ReasonerSkill
    from app.services.novel_agent.store import NovelDataStore

    provider = TextProvider("模型预测：城门冲突将升级")
    result = ReasonerSkill(NovelDataStore(), config=_skill_config(), provider=provider).execute(
        "plot_prediction", current_chapter=1, foresight_steps=2
    )

    assert result["available"] is True
    assert result["mode"] == "provider"
    assert "城门冲突" in result["generated"]


def test_reasoner_without_provider_returns_evidence_based_unavailable_prediction():
    from app.services.novel_agent.skills.reasoner import ReasonerSkill
    from app.services.novel_agent.store import ChapterData, NovelDataStore

    store = NovelDataStore(chapters=[
        ChapterData(chapter="1", title="开端", content="林远抵达城门。", index=0),
        ChapterData(chapter="2", title="冲突", content="周宁在城门拦住林远。", index=1),
    ])
    result = ReasonerSkill(store, config=_skill_config()).execute(
        "plot_prediction", current_chapter=1, foresight_steps=2
    )

    assert result["available"] is False
    assert result["status"] == "unavailable"
    assert result["predictions"]
    assert all("主角团队将遭遇更大的危机" not in item["prediction"] for item in result["predictions"])


def test_grapher_escapes_untrusted_graph_data_for_script_context(tmp_path):
    from app.services.novel_agent.skills.grapher import GrapherSkill
    from app.services.novel_agent.store import NovelDataStore

    store = NovelDataStore()
    store.graph = {
        "communities": [{"name": "<img src=x onerror=alert(1)>", "members": ["</script><script>alert(1)</script>"]}],
        "relations": [],
    }
    output = tmp_path / "graph.html"

    result = GrapherSkill(store, config=_skill_config()).execute(
        "generate_graph_html", output_path=str(output)
    )

    html = output.read_text(encoding="utf-8")
    assert result["success"] is True
    assert "</script><script>" not in html
    assert "\\u003c" in html


def test_ocr_batch_recognize_formats_json_and_srt(monkeypatch, tmp_path):
    from app.services.novel_agent.skills import ocr as ocr_module
    from app.services.novel_agent.skills.ocr import OCRSkill
    from app.services.novel_agent.store import NovelDataStore

    (tmp_path / "page.jpg").write_bytes(b"image")
    line = SimpleNamespace(text="你好", confidence=0.9, bbox=[(0, 0), (10, 10)])
    engine = SimpleNamespace(
        recognize=lambda **kwargs: SimpleNamespace(
            success=True,
            full_text="你好",
            lines=[line],
            avg_confidence=0.9,
            backend="fake",
            error="",
        )
    )
    monkeypatch.setattr(ocr_module, "ocr_engine", lambda backend: engine)
    skill = OCRSkill(NovelDataStore(), config=_skill_config())

    json_result = skill.execute(
        "ocr_batch_recognize", image_dir=str(tmp_path), output_format="json"
    )
    srt_result = skill.execute(
        "ocr_batch_recognize", image_dir=str(tmp_path), output_format="srt"
    )

    assert json.loads(json_result["formatted_output"])[0]["file"] == "page.jpg"
    assert "00:00:00,000 -->" in srt_result["formatted_output"]


def test_collector_marks_missing_source_capability_as_unavailable():
    from app.services.novel_agent.skills.collector import CollectorSkill
    from app.services.novel_agent.store import NovelDataStore

    result = CollectorSkill(NovelDataStore(), config=_skill_config()).execute(
        "collect_chapters", book_url="https://example.com/book"
    )

    assert result["status"] == "unavailable"
    assert result["available"] is False
    assert result["error_code"] == "collector_unavailable"
