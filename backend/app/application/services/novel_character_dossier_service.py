from __future__ import annotations

from typing import Any

from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService
from app.application.services.novel_emotional_arc_service import NovelEmotionalArcService
from app.application.services.novel_item_tracker_service import NovelItemTrackerService
from app.application.services.novel_character_scoring_service import NovelCharacterScoringService
from app.application.services.novel_character_memory_service import NovelCharacterMemoryService
from app.domain.entities.novel_code_analysis import CharacterCandidate


class NovelCharacterDossierService:
    """Aggregates deterministic code signals, memory vectors, and LLM profiling into a comprehensive Character Dossier."""

    def __init__(
        self,
        code_analysis_service: NovelCodeAnalysisService | None = None,
        item_tracker_service: NovelItemTrackerService | None = None,
        emotional_arc_service: NovelEmotionalArcService | None = None,
        scoring_service: NovelCharacterScoringService | None = None,
        memory_service: NovelCharacterMemoryService | None = None,
        provider_platform=None,
    ):
        self._code_service = code_analysis_service or NovelCodeAnalysisService()
        self._item_service = item_tracker_service or NovelItemTrackerService()
        self._arc_service = emotional_arc_service or NovelEmotionalArcService()
        self._scoring_service = scoring_service or NovelCharacterScoringService()
        self._memory_service = memory_service or NovelCharacterMemoryService()
        self._platform = provider_platform

    async def build_dossier(
        self,
        book_id: int,
        character_name: str,
        chapters: list[dict[str, Any]],
        llm_synthesize: bool = False,
        actor_id: str = "system",
    ) -> dict[str, Any]:
        """Builds full lifecycle profile for character_name across chapters."""
        # 1. Code Analysis for entity graph and aliases
        code_report = self._code_service.analyze(f"book-{book_id}", chapters)
        matched_candidate: CharacterCandidate | None = None
        for c in code_report.characters:
            if c.name == character_name or character_name in c.aliases:
                matched_candidate = c
                break

        if matched_candidate is None:
            matched_candidate = CharacterCandidate(
                name=character_name,
                normalized=character_name,
                count=1,
                confidence=0.75,
                aliases=[],
                importance_tier="minor",
                centrality=1.0,
            )

        search_names = list(dict.fromkeys([matched_candidate.name] + matched_candidate.aliases))

        # 2. Track Items & Props
        items_by_char = self._item_service.track_items(chapters, search_names)
        all_items: list[dict[str, Any]] = []
        for name in search_names:
            all_items.extend(items_by_char.get(name, []))

        # 3. Emotional Arc & Turning Points
        arc = self._arc_service.compute_arc(chapters, matched_candidate.name)

        # 4. Multi-dimensional Scoring
        scoring = self._scoring_service.evaluate(matched_candidate, all_items, arc)

        # 5. Index & Retrieve Memory Scenes
        await self._memory_service.index_character_scenes(book_id, chapters, [matched_candidate.name])
        top_memories = await self._memory_service.hybrid_query(
            book_id,
            matched_candidate.name,
            query_text=f"{matched_candidate.name} 核心行动 生死危机 冲突决断",
            top_k=3,
        )

        # 6. Build High-Density Summary Card
        items_summary_lines = [
            f"- 【{i['item_name']}】({i['action']})：第 {i['chapter_index']} 章《{i['chapter_title']}》- {i['excerpt'][:80]}"
            for i in all_items[:8]
        ] or ["- 暂无显著持有或使用的特殊道具"]

        tp_lines = [
            f"- 第 {tp['chapter_index']} 章《{tp['chapter_title']}》：{tp['description']} (情绪波动 {tp['delta']})"
            for tp in arc.get("turning_points", [])[:5]
        ] or ["- 情绪与心理状态平稳"]

        memory_lines = [
            f"- 第 {m['chapter_index']} 章《{m['chapter_title']}》(相关度 {m['score']})：{m['excerpt'][:120]}"
            for m in top_memories
        ] or ["- 暂无高光场景记录"]

        aliases_str = "、".join(matched_candidate.aliases) if matched_candidate.aliases else "无"
        summary_card = (
            f"# 人物深度档案卡：{matched_candidate.name}\n\n"
            f"**常用别名/称谓**：{aliases_str}\n"
            f"**定位层级**：{matched_candidate.importance_tier} | **综合评级**：【{scoring['overall_tier']} 级】(综合评分: {scoring['composite_score']})\n"
            f"**多维能力雷达**：\n"
            f"- 叙事与剧情掌控度：{scoring['plot_impact']}/100\n"
            f"- 战力与危险度：{scoring['power_score']}/100\n"
            f"- 谋略与心智深沉度：{scoring['mental_score']}/100\n\n"
            f"### 一、核心装备道具与持有物品 ({len(all_items)} 件记录)\n"
            f"{chr(10).join(items_summary_lines)}\n\n"
            f"### 二、心理与情感弧光演化 (主导心态: {arc['overall_sentiment']})\n"
            f"{chr(10).join(tp_lines)}\n\n"
            f"### 三、高光人生转折场景 (向量记忆检索)\n"
            f"{chr(10).join(memory_lines)}\n"
        )

        llm_analysis_text = ""
        if llm_synthesize and self._platform is not None:
            try:
                payload = {
                    "task": "character_dossier",
                    "character_name": matched_candidate.name,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是一位硬核文学批评家与人物深度解构专家。请依据提供的代码提取档案卡（包含角色网络、物品履历、情绪弧光与记忆切片），输出全景生平传记、心理蜕变史与人物终极命运剖析。",
                        },
                        {
                            "role": "user",
                            "content": summary_card,
                        },
                    ],
                }
                invocation = await self._platform.invoke_chat(
                    provider_group="novel_chat",
                    model=None,
                    payload=payload,
                    quota_scope=("user", actor_id),
                )
                output = invocation.get("output", {})
                llm_analysis_text = output.get("text", str(output)) if isinstance(output, dict) else str(output)
            except Exception as e:
                llm_analysis_text = f"LLM 解构生成失败: {e}"

        return {
            "character_name": matched_candidate.name,
            "aliases": matched_candidate.aliases,
            "importance_tier": matched_candidate.importance_tier,
            "centrality": matched_candidate.centrality,
            "overall_tier": scoring["overall_tier"],
            "scoring": scoring,
            "items": all_items,
            "emotional_arc": arc,
            "top_memories": top_memories,
            "summary_card": summary_card,
            "llm_analysis": llm_analysis_text,
        }
