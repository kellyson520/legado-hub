"""
Prompt 构建器

基于 NovelUnderstanding 的分层摘要系统，构建富上下文 Prompt。
目标：将 3000-4000 token 的上下文喂给 LLM，替代原始 3000 字的截断文本。
"""

from typing import List, Optional, Dict, Any

from app.domain.entities.novel import NovelBook
from .summarizer import HierarchicalSummary
from .retriever import RAGRetriever


class PromptBuilder:
    """Prompt 构建器"""

    MAX_PROMPT_CHARS = 12000  # 约 4000 token

    SYSTEM_CHARACTER = "你是一个专业的小说分析助手，擅长提取和梳理人物关系。请根据提供的角色档案、人际关系、状态变迁和事件记录进行分析。"
    SYSTEM_WORLD = "你是一个专业的小说分析助手，擅长提取和梳理世界观设定。请根据提供的地点、势力、境界体系和核心概念进行分析。"
    SYSTEM_STORYLINE = "你是一个专业的小说分析助手，擅长构建剧情时间线。请根据提供的事件记录按时间顺序梳理主线剧情。"
    SYSTEM_CHAT = "你是一个小说阅读助手，根据提供的上下文信息回答读者的问题。"

    @classmethod
    def build_character_prompt(
        cls,
        book: NovelBook,
        character_name: Optional[str] = None,
        summary: Optional[HierarchicalSummary] = None,
        retrieved_context: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        构建人物关系分析 Prompt

        Returns:
            (system_prompt, user_prompt)
        """
        parts = [f"分析小说《{book.book_name}》的人物关系。"]

        if summary:
            parts.append(summary.to_prompt_context(priority="p0"))  # 实体卡片

        if retrieved_context:
            parts.append(retrieved_context)

        user_prompt = cls._trim("\n\n".join(parts))
        return cls.SYSTEM_CHARACTER, user_prompt

    @classmethod
    def build_world_prompt(
        cls,
        book: NovelBook,
        summary: Optional[HierarchicalSummary] = None,
        retrieved_context: Optional[str] = None,
    ) -> tuple[str, str]:
        """构建世界观分析 Prompt"""
        parts = [f"分析小说《{book.book_name}》的世界观设定。"]

        if summary:
            parts.append(summary.to_prompt_context(priority="p2"))  # 篇章 + 全局

        if retrieved_context:
            parts.append(retrieved_context)

        user_prompt = cls._trim("\n\n".join(parts))
        return cls.SYSTEM_WORLD, user_prompt

    @classmethod
    def build_storyline_prompt(
        cls,
        book: NovelBook,
        summary: Optional[HierarchicalSummary] = None,
        retrieved_context: Optional[str] = None,
    ) -> tuple[str, str]:
        """构建剧情时间线 Prompt"""
        parts = [f"分析小说《{book.book_name}》的剧情时间线。"]

        if summary:
            parts.append(summary.to_prompt_context(priority="p1"))  # 章节摘要
            parts.append(summary.to_prompt_context(priority="p2"))  # 篇章摘要

        if retrieved_context:
            parts.append(retrieved_context)

        user_prompt = cls._trim("\n\n".join(parts))
        return cls.SYSTEM_STORYLINE, user_prompt

    @classmethod
    def build_chat_prompt(
        cls,
        book: NovelBook,
        question: str,
        summary: Optional[HierarchicalSummary] = None,
        retrieved_context: Optional[str] = None,
    ) -> tuple[str, str]:
        """构建智能问答 Prompt"""
        parts = [f"关于小说《{book.book_name}》的问题：{question}"]

        if summary:
            # 问答需要全层级上下文
            parts.append(summary.to_prompt_context(priority="all"))

        if retrieved_context:
            parts.append(f"【相关检索结果】\n{retrieved_context}")

        user_prompt = cls._trim("\n\n".join(parts))
        return cls.SYSTEM_CHAT, user_prompt

    @classmethod
    def build_fix_prompt(
        cls,
        source_url: str,
        error_msg: Optional[str] = None,
        source_config: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:
        """构建书源修复 Prompt"""
        system = "你是 Legado 书源调试专家，擅长修复失效书源。"
        parts = [f"书源URL: {source_url}"]
        if error_msg:
            parts.append(f"错误信息: {error_msg}")
        if source_config:
            import json
            parts.append(f"当前配置:\n```json\n{json.dumps(source_config, ensure_ascii=False, indent=2)}\n```")
        parts.append("请分析问题并给出修复建议，以JSON格式输出修复后的配置和修复说明。")
        return system, cls._trim("\n".join(parts))

    @classmethod
    def build_review_prompt(cls, text: str) -> tuple[str, str]:
        """构建内容审查 Prompt"""
        system = "你是内容安全审查助手，判断文本是否合规。"
        user = f"请审查以下内容的合规性，检查是否包含违法、暴力、色情等不当内容。\n\n内容:\n{text[:5000]}"
        return system, user

    @classmethod
    def _trim(cls, text: str) -> str:
        """截断文本到最大长度"""
        if len(text) > cls.MAX_PROMPT_CHARS:
            return text[:cls.MAX_PROMPT_CHARS] + "\n...[内容截断]"
        return text
