"""Compact, deterministic memory cards for novel retrieval and embeddings."""

from __future__ import annotations

import hashlib
import json
from typing import Any


MAX_CARD_CHARS = 1600


def entity_memory_card(entity, evidence_limit: int = 3) -> str:
    entity_type = _value(getattr(entity, "entity_type", "entity"))
    aliases = _join(getattr(entity, "aliases", []))
    attributes = dict(getattr(entity, "attributes", {}) or {})
    confidence = _number(attributes.get("confidence"), 0.0)
    evidence = _evidence(attributes.get("evidence"), evidence_limit)
    attribute_text = _compact_attributes(attributes, excluded={"evidence"})
    lines = [
        f"实体|名称: {getattr(entity, 'name', '')}|类型: {entity_type}",
        f"别名: {aliases or '无'}|章节: {getattr(entity, 'first_appearance_ch', 0)}-{getattr(entity, 'last_appearance_ch', 0)}",
        f"出现: {getattr(entity, 'appearance_count', 0)}|重要度: {getattr(entity, 'importance_score', 3)}/5|置信度: {confidence:.2f}",
        f"描述: {getattr(entity, 'description', '') or '无'}",
        f"属性: {attribute_text or '无'}",
    ]
    if evidence:
        lines.append("证据: " + "；".join(evidence))
    return _bound("\n".join(lines))


def event_memory_card(event, evidence_limit: int = 2) -> str:
    event_type = _value(getattr(event, "event_type", "custom"))
    participants = _join(getattr(event, "participants", []))
    evidence = _evidence(getattr(event, "evidence", []), evidence_limit)
    confidence = _number(getattr(event, "confidence", 0.8), 0.8)
    lines = [
        f"事件|第{getattr(event, 'chapter_num', 0)}章|类型: {event_type}",
        f"描述: {getattr(event, 'description', '')}|参与者: {participants or '无'}",
        f"地点: {getattr(event, 'location', '') or '未知'}|重要度: {getattr(event, 'importance', 3)}/5|置信度: {confidence:.2f}",
    ]
    if evidence:
        lines.append("证据: " + "；".join(evidence))
    return _bound("\n".join(lines))


def state_memory_card(state, evidence_limit: int = 2) -> str:
    field_name = _value(getattr(state, "field_name", "custom"))
    evidence = _evidence(getattr(state, "evidence", []), evidence_limit)
    confidence = _number(getattr(state, "confidence", 0.8), 0.8)
    lines = [
        f"状态|第{getattr(state, 'chapter_num', 0)}章|实体: {getattr(state, 'entity_name', '')}|字段: {field_name}",
        f"变化: {getattr(state, 'before_value', '') or '空'} -> {getattr(state, 'after_value', '') or '空'}",
        f"触发: {getattr(state, 'trigger_event', '') or '未知'}|置信度: {confidence:.2f}",
    ]
    if evidence:
        lines.append("证据: " + "；".join(evidence))
    return _bound("\n".join(lines))


def memory_card_hash(card: str) -> str:
    return hashlib.sha256(card.encode("utf-8")).hexdigest()


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _number(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _join(values: Any) -> str:
    if not isinstance(values, (list, tuple, set)):
        return str(values or "")
    return ", ".join(str(value) for value in values if str(value).strip())


def _compact_attributes(attributes: dict[str, Any], excluded: set[str]) -> str:
    values = {
        str(key): value
        for key, value in attributes.items()
        if key not in excluded and value not in (None, "", [], {})
    }
    if not values:
        return ""
    return _clip(json.dumps(values, ensure_ascii=False, default=str), 420)


def _evidence(values: Any, limit: int) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    selected: list[str] = []
    for item in list(values)[: max(0, int(limit))]:
        if isinstance(item, dict):
            chapter = item.get("chapter_num", item.get("chapter_id", "?"))
            text = item.get("text", item.get("excerpt", ""))
            selected.append(f"第{chapter}章: {_clip(str(text), 220)}")
        else:
            selected.append(_clip(str(item), 220))
    return [item for item in selected if item.strip()]


def _clip(value: str, length: int) -> str:
    value = " ".join(str(value).split())
    return value if len(value) <= length else value[: max(0, length - 1)] + "…"


def _bound(value: str) -> str:
    return _clip(value, MAX_CARD_CHARS)
