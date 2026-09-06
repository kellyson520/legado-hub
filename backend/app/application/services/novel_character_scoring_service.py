from __future__ import annotations

from typing import Any
from app.domain.entities.novel_code_analysis import CharacterCandidate


class NovelCharacterScoringService:
    """Comprehensive Six-Dimensional Capability Matrix and Tiering System for characters."""

    _LETHAL_ITEMS: set[str] = {
        "C4炸药", "炸药", "手枪", "冲锋枪", "狙击枪", "手雷", "匕首", "短刀",
        "鬼眼", "鬼烛", "柴刀", "替死娃娃", "鬼绳", "黄金箱", "羊皮纸", "鬼影",
        "刀", "枪", "剑", "戟", "矛", "弓", "槊", "鞭", "斧",
    }

    def evaluate(
        self,
        character: CharacterCandidate,
        items: list[dict[str, Any]],
        arc: dict[str, Any],
    ) -> dict[str, Any]:
        """Calculates 6-dimensional capability matrix, radar, and tiering."""
        trajectory = arc.get("trajectory", [])
        affect = arc.get("affective_tensor", {})
        turning_points = arc.get("turning_points", [])

        # 1. 武勇与绝杀 (Combat & Prowess)
        weapon_items = [i for i in items if i.get("category") == "weapon" or any(l in i["item_name"] for l in self._LETHAL_ITEMS)]
        weapon_score = min(len(weapon_items) * 20.0, 45.0)
        actions_used = sum(1 for i in items if i.get("action") == "used")
        action_combat_score = min(actions_used * 8.0, 25.0)
        affect_combat = min((affect.get("怒", 0.0) + affect.get("雄", 0.0)) * 2.0, 20.0)
        mount_combat = 10.0 if any(i.get("category") == "mount" or any(m in i["item_name"] for m in ("马", "驹", "兽", "车")) for i in items) else 0.0
        tier_base_combat = 15.0 if character.importance_tier == "protagonist" else (10.0 if character.importance_tier == "major" else 5.0)
        combat_prowess = round(min(weapon_score + action_combat_score + affect_combat + mount_combat + tier_base_combat + 10.0, 100.0), 1)

        # 2. 智谋与策论 (Strategy & Intellect)
        base_intellect = 45.0
        alias_intellect = min(len(character.aliases) * 8.0, 25.0)
        calm_count = sum(1 for t in trajectory if t.get("dominant_emotion") in ("从容", "冷静", "自信", "悠闲", "雄傲"))
        calm_intellect = min(calm_count * 6.0 + affect.get("疑", 0.0) * 2.0, 20.0)
        strategy_intellect = round(min(base_intellect + alias_intellect + calm_intellect + (10.0 if character.importance_tier in ("protagonist", "major") else 0.0), 100.0), 1)

        # 3. 统御与声望 (Command & Authority)
        title_keywords = ("将", "相", "侯", "主", "总", "队", "君", "督", "王", "帝")
        title_count = sum(1 for a in character.aliases if any(t in a for t in title_keywords))
        title_score = min(title_count * 15.0, 35.0)
        centrality_score = min(character.centrality * 3.0, 35.0)
        affect_authority = min(affect.get("雄", 0.0) * 2.5, 20.0)
        command_authority = round(min(title_score + centrality_score + affect_authority + (10.0 if character.importance_tier == "protagonist" else 5.0), 100.0), 1)

        # 4. 气节与风骨 (Morale & Resilience)
        loyalty_score = min(affect.get("忠", 0.0) * 4.0, 40.0)
        has_recovery = any(tp.get("shift") == "surge" for tp in turning_points)
        recovery_score = 25.0 if has_recovery else (15.0 if len(turning_points) > 0 else 5.0)
        calm_morale = min(calm_count * 5.0, 15.0)
        morale_resilience = round(min(loyalty_score + recovery_score + calm_morale + 20.0, 100.0), 1)

        # 5. 宝器与神兵 (Artifacts & Mounts)
        items_count_score = min(len(items) * 12.0, 40.0)
        rare_items = [i for i in items if i.get("category") in ("weapon", "mount", "artifact")]
        rare_score = min(len(rare_items) * 15.0, 40.0)
        mount_bonus = 20.0 if any(i.get("category") == "mount" or any(m in i["item_name"] for m in ("马", "驹", "车", "兽")) for i in items) else 0.0
        combo_bonus = 15.0 if any(i.get("category") == "weapon" for i in items) and mount_bonus > 0 else 0.0
        artifacts_mounts = round(min(items_count_score + rare_score + mount_bonus + combo_bonus, 100.0), 1)

        # 6. 命途与支配 (Plot Centrality)
        freq_points = min(character.count * 1.5, 45.0)
        central_points = min(character.centrality * 2.5, 35.0)
        tier_points = 20.0 if character.importance_tier == "protagonist" else (10.0 if character.importance_tier == "major" else 0.0)
        tp_points = min(len(turning_points) * 5.0, 15.0)
        plot_centrality = round(min(freq_points + central_points + tier_points + tp_points, 100.0), 1)

        # Six-dimensional capability matrix
        capability_matrix = {
            "武勇绝杀": {"score": combat_prowess, "title": "个人战力与杀伐决断", "level": "绝巅" if combat_prowess >= 85 else ("精悍" if combat_prowess >= 60 else "寻常")},
            "智谋策论": {"score": strategy_intellect, "title": "运筹帷幄与智计深沉", "level": "鬼谋" if strategy_intellect >= 85 else ("明睿" if strategy_intellect >= 60 else "寻常")},
            "统御声望": {"score": command_authority, "title": "军政统帅与天下重望", "level": "八荒咸服" if command_authority >= 85 else ("一方之秀" if command_authority >= 60 else "平民")},
            "气节风骨": {"score": morale_resilience, "title": "忠义气节与逆境风骨", "level": "千秋凛然" if morale_resilience >= 85 else ("坚毅" if morale_resilience >= 60 else "随波")},
            "宝器神兵": {"score": artifacts_mounts, "title": "名兵神驹与造化机缘", "level": "神器尽出" if artifacts_mounts >= 80 else ("兵甲精良" if artifacts_mounts >= 50 else "两手空空")},
            "命途支配": {"score": plot_centrality, "title": "全剧因果与叙事掌控", "level": "天命核心" if plot_centrality >= 85 else ("关键砥柱" if plot_centrality >= 60 else "旁观边缘")},
        }

        # Overall composite calculation
        composite = (
            combat_prowess * 0.20
            + strategy_intellect * 0.15
            + command_authority * 0.15
            + morale_resilience * 0.15
            + artifacts_mounts * 0.15
            + plot_centrality * 0.20
        )
        composite = round(composite, 1)

        if composite >= 92.0 or (plot_centrality >= 85.0 and (combat_prowess >= 85.0 or strategy_intellect >= 85.0)):
            overall_tier = "SS" if composite < 96.0 else "SSS"
        elif composite >= 75.0 or (plot_centrality >= 70.0 and combat_prowess >= 60.0):
            overall_tier = "S"
        elif composite >= 55.0 or character.importance_tier == "protagonist":
            overall_tier = "A"
        elif composite >= 40.0:
            overall_tier = "B"
        else:
            overall_tier = "C"

        return {
            "character_name": character.name,
            "overall_tier": overall_tier,
            "composite_score": composite,
            "capability_matrix": capability_matrix,
            # Backwards compatibility fields
            "plot_impact": plot_centrality,
            "power_score": combat_prowess,
            "mental_score": strategy_intellect,
            "radar": {
                "武勇绝杀": combat_prowess,
                "智谋策论": strategy_intellect,
                "统御声望": command_authority,
                "气节风骨": morale_resilience,
                "宝器神兵": artifacts_mounts,
                "命途支配": plot_centrality,
            },
        }
