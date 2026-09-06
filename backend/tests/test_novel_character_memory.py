import pytest
from app.application.services.novel_character_memory_service import NovelCharacterMemoryService


@pytest.mark.asyncio
async def test_character_memory_indexing_and_hybrid_retrieval():
    chapters = [
        {
            "chapter_id": 1,
            "chapter_index": 1,
            "title": "梦境与劫案",
            "content": "林弦戴着奥特曼面具，站在金库密码门前，手速飞快地计算着斐波那契数列与破译密码。",
        },
        {
            "chapter_id": 2,
            "chapter_index": 2,
            "title": "咖啡馆的日常",
            "content": "林弦坐在咖啡馆里，和赵英珺闲聊关于新季度的市场战略规划，窗外阳光明媚。",
        },
        {
            "chapter_id": 3,
            "chapter_index": 3,
            "title": "C4引爆",
            "content": "大脸猫喊道：快退后！林弦果断按下了C4炸药的引爆按钮，伴随着剧烈轰鸣，墙体被彻底撕裂！",
        },
    ]

    service = NovelCharacterMemoryService()
    indexed_count = await service.index_character_scenes(
        book_id=101,
        chapters=chapters,
        character_names=["林弦", "大脸猫"],
    )
    assert indexed_count >= 3

    # Query 1: Retrieve memory about bomb explosion
    bomb_memories = await service.hybrid_query(
        book_id=101,
        character_name="林弦",
        query_text="引爆炸药与墙体轰鸣",
        top_k=1,
    )
    assert len(bomb_memories) == 1
    top_memory = bomb_memories[0]
    assert top_memory["chapter_index"] == 3
    assert "C4" in top_memory["excerpt"] or "炸药" in top_memory["excerpt"]
    assert top_memory["score"] > 0.0

    # Query 2: Retrieve memory about bank safe & password
    password_memories = await service.hybrid_query(
        book_id=101,
        character_name="林弦",
        query_text="金库与破译密码计算",
        top_k=1,
    )
    assert len(password_memories) == 1
    assert password_memories[0]["chapter_index"] == 1
    assert "密码" in password_memories[0]["excerpt"]
