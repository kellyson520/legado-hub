import pytest
from app.application.services.novel_agent_service import NovelAgentService
from app.domain.entities.novel_runtime import NovelIngestion


def test_build_payload_creates_dense_structural_digest_reducing_tokens():
    # Long text representing multiple chapters with a battle climax
    ch1 = "第一章：宁静的小镇。林弦和小林在书房商讨未来。窗外微风拂过，一切都很安详。" * 60
    ch2 = "第二章：惊天危机。突然，大脸猫手持冲锋枪冲了进来！嘭！子弹撕裂了墙壁，鲜血四溅，C4炸药急速倒计时！轰然巨响，火光吞没了整个仓库！" * 60
    full_text = ch1 + "\n\n" + ch2

    ingestion = NovelIngestion(
        id="novel-digest-1",
        book_id=10,
        title="超能俱乐部",
        source_text=full_text,
    )

    payload = NovelAgentService._build_payload(ingestion)
    user_msg = payload["messages"][1]["content"]

    # 1. Verification of significant compression (< 3,500 chars instead of 6,000+ full text)
    assert len(user_msg) <= 3500
    assert len(user_msg) < len(full_text) * 0.5

    # 2. Verification of structured insights embedded for the LLM
    assert "核心角色与网络" in user_msg or "角色图谱" in user_msg or "林弦" in user_msg
    assert "高能/高潮场景" in user_msg or "核心冲突" in user_msg or "爆炸" in user_msg or "炸药" in user_msg
    assert "时序与事件节点" in user_msg or "时间" in user_msg or "事件" in user_msg


def test_novel_agent_service_query_tools():
    service = NovelAgentService()
    text = "林弦走入长安。小林端起茶水。大脸猫持枪冲入，炸药瞬间引爆！"
    tools = service.get_analysis_tools_definitions()
    
    tool_names = [t["name"] for t in tools]
    assert "get_character_graph" in tool_names
    assert "get_timeline" in tool_names
    assert "get_climax_scenes" in tool_names

    # Direct execution of tools
    graph = service.tool_get_character_graph("测试小说", text)
    assert "nodes" in graph or "characters" in graph

    climaxes = service.tool_get_climax_scenes("测试小说", text)
    assert isinstance(climaxes, list)
    assert len(climaxes) > 0
