"""
角色状态变迁追踪器

追踪实体在小说中的属性变化：境界、能力、状态、关系、物品、位置、情绪
"""

from typing import List, Dict, Any, Optional

from app.domain.entities.novel import NovelStateChange, StateField, NovelEntity


class StateTracker:
    """状态变迁追踪器"""

    @classmethod
    def track_entity_states(
        cls,
        state_changes: List[NovelStateChange],
        entity_name: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        追踪实体状态变化轨迹

        Returns:
            {entity_name: [{chapter_num, field_name, before, after, trigger}]}
        """
        result: Dict[str, List[Dict[str, Any]]] = {}

        for sc in sorted(state_changes, key=lambda x: x.chapter_num):
            if entity_name and sc.entity_name != entity_name:
                continue

            if sc.entity_name not in result:
                result[sc.entity_name] = []

            result[sc.entity_name].append({
                "chapter_num": sc.chapter_num,
                "field_name": sc.field_name.value,
                "before_value": sc.before_value,
                "after_value": sc.after_value,
                "trigger_event": sc.trigger_event,
                "confidence": sc.confidence,
            })

        return result

    @classmethod
    def get_current_state(
        cls,
        state_changes: List[NovelStateChange],
        entity_name: str,
        field_name: Optional[StateField] = None,
    ) -> Dict[str, str]:
        """获取实体当前最新状态"""
        current: Dict[str, str] = {}

        filtered = [sc for sc in state_changes if sc.entity_name == entity_name]
        if field_name:
            filtered = [sc for sc in filtered if sc.field_name == field_name]

        for sc in sorted(filtered, key=lambda x: x.chapter_num):
            current[sc.field_name.value] = sc.after_value

        return current

    @classmethod
    def detect_major_breakthroughs(
        cls,
        state_changes: List[NovelStateChange],
        entity_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """检测重大突破事件（境界跃迁、能力觉醒等）"""
        breakthroughs = []

        filtered = state_changes
        if entity_name:
            filtered = [sc for sc in filtered if sc.entity_name == entity_name]

        for sc in sorted(filtered, key=lambda x: x.chapter_num):
            if sc.field_name == StateField.REALM and sc.before_value != sc.after_value:
                breakthroughs.append({
                    "entity": sc.entity_name,
                    "chapter_num": sc.chapter_num,
                    "type": "realm_breakthrough",
                    "from": sc.before_value,
                    "to": sc.after_value,
                    "trigger": sc.trigger_event,
                })
            elif sc.field_name == StateField.ABILITY and sc.before_value != sc.after_value:
                breakthroughs.append({
                    "entity": sc.entity_name,
                    "chapter_num": sc.chapter_num,
                    "type": "ability_awakening",
                    "from": sc.before_value,
                    "to": sc.after_value,
                    "trigger": sc.trigger_event,
                })

        return breakthroughs

    @classmethod
    def generate_state_summary(
        cls,
        state_changes: List[NovelStateChange],
        entity_name: str,
        max_length: int = 300,
    ) -> str:
        """生成实体状态变迁摘要文本"""
        changes = cls.track_entity_states(state_changes, entity_name)
        if entity_name not in changes or not changes[entity_name]:
            return f"{entity_name} 暂无状态记录。"

        lines = [f"【{entity_name} 状态变迁】"]
        for c in changes[entity_name]:
            lines.append(
                f"第{c['chapter_num']}章: {c['field_name']} "
                f"从 [{c['before_value']}] 变为 [{c['after_value']}]"
            )

        summary = "\n".join(lines)
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
        return summary
