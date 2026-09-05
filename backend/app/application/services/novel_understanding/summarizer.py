"""
分层摘要生成器

Token 预算体系：
- P0 实体卡片: ~400 token（核心实体列表）
- P1 章节摘要: ~1500 token（章节摘要 + 关键事件）
- P2 状态变化: ~800 token（角色状态变迁 + 篇章摘要）
- P3 全局摘要: ~300 token（全书主线概括）

总计: ~3000-4000 token
"""

from typing import List, Dict, Any
from dataclasses import dataclass, field

from app.domain.entities.novel import NovelBook, NovelChapter, NovelEntity, NovelEvent


@dataclass
class HierarchicalSummary:
    """分层摘要结构"""
    book_id: int
    # P0: 实体卡片
    entity_cards: List[Dict[str, Any]] = field(default_factory=list)
    # P1: 章节摘要 + 关键事件
    chapter_summaries: List[Dict[str, Any]] = field(default_factory=list)
    # P2: 状态变化 + 篇章摘要
    arc_summaries: List[Dict[str, Any]] = field(default_factory=list)
    state_changes_summary: str = ""
    # P3: 全局摘要
    global_summary: str = ""
    # Token 统计
    estimated_tokens: int = 0

    def to_prompt_context(self, priority: str = "all") -> str:
        """将摘要转为 LLM Prompt 上下文文本"""
        parts = []
        if priority in ("all", "p3", "global"):
            if self.global_summary:
                parts.append(f"【全书概要】\n{self.global_summary}\n")
        if priority in ("all", "p2", "arc"):
            if self.arc_summaries:
                parts.append("【篇章概要】")
                for arc in self.arc_summaries:
                    parts.append(f"  {arc.get('arc_tag', '')}: {arc.get('summary', '')}")
                parts.append("")
            if self.state_changes_summary:
                parts.append(f"【角色状态变化】\n{self.state_changes_summary}\n")
        if priority in ("all", "p1", "chapter"):
            if self.chapter_summaries:
                parts.append("【近期章节】")
                for ch in self.chapter_summaries[-5:]:  # 最近5章
                    parts.append(f"  第{ch.get('chapter_num', '?')}章: {ch.get('summary', '')}")
                parts.append("")
        if priority in ("all", "p0", "entity"):
            if self.entity_cards:
                parts.append("【核心人物】")
                for card in self.entity_cards[:10]:  # 前10个
                    parts.append(f"  {card.get('name', '')}: {card.get('description', '')}")
                parts.append("")
        return "\n".join(parts)


class HierarchicalSummarizer:
    """分层摘要生成器"""

    # Prompt 模板
    CHAPTER_SUMMARY_PROMPT = """请对以下小说章节进行摘要，要求：
1. 摘要长度控制在 100 字以内
2. 提取 1-3 个关键事件
3. 列出出现的主要人物

章节内容：
{text}

请以 JSON 格式输出：
{{"summary": "摘要", "key_events": ["事件1"], "characters": ["人物1"]}}"""

    ARC_SUMMARY_PROMPT = """以下是同一篇章的多个章节摘要，请合并为一个篇章摘要：

{chapter_summaries}

请输出：篇章标题 + 100字以内摘要"""

    GLOBAL_SUMMARY_PROMPT = """请根据以下信息生成全书主线摘要（200字以内）：

已提取实体：
{entities}

关键事件时间线：
{events}

摘要要求：突出主线剧情、核心冲突、主角成长轨迹。"""

    @classmethod
    def build_chapter_summary_prompt(cls, chapter_text: str) -> str:
        return cls.CHAPTER_SUMMARY_PROMPT.format(text=chapter_text[:6000])

    @classmethod
    def parse_chapter_summary(cls, llm_response: str) -> Dict[str, Any]:
        """解析 LLM 章节摘要响应"""
        import json
        import re
        text = llm_response.strip()
        # 提取 JSON
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            text = m.group(1)
        elif text.startswith("{") and text.endswith("}"):
            pass
        else:
            return {"summary": text[:200], "key_events": [], "characters": []}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"summary": text[:200], "key_events": [], "characters": []}

    @classmethod
    def build_arc_summary_prompt(cls, chapter_summaries: List[Dict[str, Any]]) -> str:
        texts = []
        for ch in chapter_summaries:
            texts.append(f"第{ch.get('chapter_num', '?')}章: {ch.get('summary', '')}")
        return cls.ARC_SUMMARY_PROMPT.format(chapter_summaries="\n".join(texts))

    @classmethod
    def build_global_summary_prompt(
        cls,
        entities: List[NovelEntity],
        events: List[NovelEvent],
    ) -> str:
        entity_lines = []
        for e in entities[:20]:
            entity_lines.append(f"- {e.name} ({e.entity_type.value}): {e.description}")

        event_lines = []
        for ev in sorted(events, key=lambda x: x.chapter_num)[:15]:
            event_lines.append(f"- 第{ev.chapter_num}章: {ev.description}")

        return cls.GLOBAL_SUMMARY_PROMPT.format(
            entities="\n".join(entity_lines),
            events="\n".join(event_lines),
        )

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """估算文本的 token 数（中文字符按 1.5 token 计）"""
        # 简单估算：中文 ≈ 1.5 token/字，英文 ≈ 0.25 token/字符
        cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - cn_chars
        return int(cn_chars * 1.5 + other_chars * 0.25)

    @classmethod
    def build_entity_cards(cls, entities: List[NovelEntity]) -> List[Dict[str, Any]]:
        """将实体列表转为实体卡片（P0 层级）"""
        cards = []
        for e in sorted(entities, key=lambda x: x.importance_score, reverse=True)[:20]:
            card = {
                "name": e.name,
                "type": e.entity_type.value,
                "description": e.description[:100],
                "aliases": e.aliases[:3],
                "attributes": e.attributes,
                "first_appearance": e.first_appearance_ch,
            }
            cards.append(card)
        return cards
