"""
实体提取器

提供：
1. 结构化 Prompt 模板（供 LLM 调用）
2. LLM 响应解析器（JSON → 领域实体）
3. 批量提取编排

实体类型：人物/地点/物品/势力/境界/概念
"""

import json
import re
from typing import List, Dict, Any, Optional

from app.domain.entities.novel import (
    NovelEntity, NovelRelationship, NovelEvent, NovelStateChange,
    EntityType, RelationType, EventType, StateField,
)


class EntityExtractor:
    """实体提取器 - Prompt + 解析器"""

    # ========== Prompt 模板 ==========

    ENTITY_PROMPT = """你是一个专业的小说分析助手。请仔细阅读以下章节内容，提取其中出现的所有实体。

【章节内容】
{chapter_text}

【已知的实体词典】（可能为空）
{known_entities}

【输出格式】
请以 JSON 格式输出，字段如下：
{{
  "characters": [
    {{"name": "实体名称", "aliases": ["别名1"], "description": "简要描述", "attributes": {{"gender": "男", "age": 20}}}}
  ],
  "locations": [
    {{"name": "地点名称", "description": "描述"}}
  ],
  "items": [
    {{"name": "物品名称", "description": "描述"}}
  ],
  "factions": [
    {{"name": "势力名称", "description": "描述"}}
  ],
  "realms": [
    {{"name": "境界名称", "description": "描述"}}
  ],
  "concepts": [
    {{"name": "概念名称", "description": "描述"}}
  ],
  "relationships": [
    {{"source": "源实体", "target": "目标实体", "relation_type": "关系类型", "description": "描述"}}
  ],
  "events": [
    {{"event_type": "事件类型", "description": "事件描述", "participants": ["参与者"], "location": "地点", "importance": 3}}
  ],
  "state_changes": [
    {{"entity_name": "实体名", "field_name": "状态字段", "before_value": "变化前", "after_value": "变化后", "trigger_event": "触发事件"}}
  ]
}}

关系类型可选值：ally, enemy, master, subordinate, lover, family, rival, custom
事件类型可选值：battle, breakthrough, betrayal, reunion, discovery, departure, death, custom
状态字段可选值：realm, ability, status, relationship, possession, position, emotion, custom

请确保 JSON 格式正确，不要输出任何其他文字。"""

    # ========== 解析器 ==========

    @classmethod
    def parse_llm_response(cls, text: str, book_id: int = 0, chapter_id: int = 0, chapter_num: int = 0) -> Dict[str, List[Any]]:
        """解析 LLM JSON 输出为领域实体列表"""
        # 提取 JSON 块
        json_str = cls._extract_json(text)
        if not json_str:
            return {"entities": [], "relationships": [], "events": [], "state_changes": []}

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return {"entities": [], "relationships": [], "events": [], "state_changes": []}

        entities = []
        relationships = []
        events = []
        state_changes = []

        # 解析各类实体
        type_map = {
            "characters": EntityType.CHARACTER,
            "locations": EntityType.LOCATION,
            "items": EntityType.ITEM,
            "factions": EntityType.FACTION,
            "realms": EntityType.REALM,
            "concepts": EntityType.CONCEPT,
        }

        for key, entity_type in type_map.items():
            for item in data.get(key, []):
                entity = NovelEntity(
                    book_id=book_id,
                    name=item.get("name", ""),
                    aliases=item.get("aliases", []),
                    entity_type=entity_type,
                    description=item.get("description", ""),
                    first_appearance_ch=chapter_num,
                    last_appearance_ch=chapter_num,
                    appearance_count=1,
                    attributes=item.get("attributes", {}),
                )
                entities.append(entity)

        # 解析关系
        for item in data.get("relationships", []):
            rel_type = item.get("relation_type", "custom")
            try:
                rel_enum = RelationType(rel_type)
            except ValueError:
                rel_enum = RelationType.CUSTOM

            rel = NovelRelationship(
                book_id=book_id,
                source_entity=item.get("source", ""),
                target_entity=item.get("target", ""),
                relation_type=rel_enum,
                description=item.get("description", ""),
                since_chapter=chapter_num,
            )
            relationships.append(rel)

        # 解析事件
        for item in data.get("events", []):
            ev_type = item.get("event_type", "custom")
            try:
                ev_enum = EventType(ev_type)
            except ValueError:
                ev_enum = EventType.CUSTOM

            ev = NovelEvent(
                book_id=book_id,
                chapter_id=chapter_id,
                chapter_num=chapter_num,
                event_type=ev_enum,
                description=item.get("description", ""),
                participants=item.get("participants", []),
                location=item.get("location", ""),
                importance=item.get("importance", 3),
            )
            events.append(ev)

        # 解析状态变更
        for item in data.get("state_changes", []):
            field = item.get("field_name", "custom")
            try:
                field_enum = StateField(field)
            except ValueError:
                field_enum = StateField.CUSTOM

            sc = NovelStateChange(
                book_id=book_id,
                entity_name=item.get("entity_name", ""),
                chapter_id=chapter_id,
                chapter_num=chapter_num,
                field_name=field_enum,
                before_value=item.get("before_value", ""),
                after_value=item.get("after_value", ""),
                trigger_event=item.get("trigger_event", ""),
            )
            state_changes.append(sc)

        return {
            "entities": entities,
            "relationships": relationships,
            "events": events,
            "state_changes": state_changes,
        }

    @classmethod
    def _extract_json(cls, text: str) -> str:
        """从文本中提取 JSON 块"""
        text = text.strip()
        # 尝试直接解析
        if text.startswith("{") and text.endswith("}"):
            return text
        # 尝试提取 ```json ... ``` 块
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            return m.group(1)
        # 尝试提取 { ... } 块
        m = re.search(r'(\{.*\})', text, re.DOTALL)
        if m:
            return m.group(1)
        return text

    @classmethod
    def build_prompt(cls, chapter_text: str, known_entities: List[str] = None) -> str:
        """构建实体提取 Prompt"""
        known_str = "\n".join(f"- {e}" for e in (known_entities or [])) or "无"
        return cls.ENTITY_PROMPT.format(
            chapter_text=chapter_text[:8000],  # 限制长度
            known_entities=known_str,
        )
