from app.application.services.novel_agent_service import NovelAgentService
from app.domain.entities.novel_runtime import NovelIngestion


def test_build_payload_bounds_source_text_for_llm_context():
    long_text = "段落内容 " * 50000
    ingestion = NovelIngestion(
        id="test-ingestion",
        book_id=1,
        title="测试小说",
        source_text=long_text,
    )
    payload = NovelAgentService._build_payload(ingestion)
    
    assert len(payload["text"]) <= 16000
    user_msg = payload["messages"][1]["content"]
    assert len(user_msg) <= 20000
    assert "小说标题: 测试小说" in user_msg
