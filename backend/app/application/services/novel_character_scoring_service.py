from __future__ import annotations

from typing import Any
from app.domain.entities.novel_code_analysis import CharacterCandidate


class NovelCharacterScoringService:
    """Evaluates multi-dimensional capacity, psychological resilience, combat power, and narrative impact."""

    _LETHAL_ITEMS: set[str] = {
        "C4炸药", "炸药", "手枪", "冲锋枪", "狙击枪", "手雷", "匕首", "短刀",
        "鬼眼", "鬼烛", "柴刀", "替死娃娃", "鬼绳", "黄金箱", "羊皮纸", "鬼影",
    }

    def evaluate(
        self,
        character: CharacterCandidate,
        items: list[dict[str, Any]],
        arc: dict[str, Any],
    ) -> dict[str, Any]:
        """Calculates mental_score, power_score, plot_impact, and overall_tier."""
        # 1. Plot Impact (0-100)
        freq_points = min(character.count * 1.2, 40.0)
        centrality_points = min(character.centrality * 2.5, 30.0)
        tier_points = 20.0 if character.importance_tier == "protagonist" else (10.0 if character.importance_tier == "major" else 0.0)
        tp_points = min(len(arc.get("turning_points", [])) * 5.0, 10.0)
        plot_impact = round(min(freq_points + centrality_points + tier_points + tp_points, 100.0), 1)

        # 2. Power & Danger Score (0-100)
        base_power = 25.0
        lethal_matches = {i["item_name"] for i in items if any(l in i["item_name"] for l in self._LETHAL_ITEMS)}
        lethal_points = min(len(lethal_matches) * 16.0, 45.0)
        actions_used = sum(1 for i in items if i.get("action") == "used")
        used_points = min(actions_used * 6.0, 18.0)
        tier_power = 15.0 if character.importance_tier in ("protagonist", "major") else 0.0
        power_score = round(min(base_power + lethal_points + used_points + tier_power, 100.0), 1)

        # 3. Mental & Strategy Score (0-100)
        base_mental = 45.0
        alias_points = min(len(character.aliases) * 8.0, 20.0)
        
        trajectory = arc.get("trajectory", [])
        calm_count = sum(1 for t in trajectory if t.get("dominant_emotion") in ("从容", "冷静", "自信", "悠闲"))
        calm_points = min(calm_count * 8.0, 20.0)
        has_recovery = any(tp.get("shift") == "surge" for tp in arc.get("turning_points", []))
        recovery_points = 15.0 if has_recovery else 0.0
        mental_score = round(min(base_mental + alias_points + calm_points + recovery_points, 100.0), 1)

        # 4. Overall Tier
        composite = (plot_impact * 0.4) + (power_score * 0.3) + (mental_score * 0.3)
        if composite >= 75.0 or (plot_impact >= 80.0 and power_score >= 60.0):
            overall_tier = "S"
        elif composite >= 60.0:
            overall_tier = "A"
        elif composite >= 40.0:
            overall_tier = "B"
        else:
            overall_tier = "C"

        return {
            "character_name": character.name,
            "overall_tier": overall_tier,
            "composite_score": round(composite, 1),
            "plot_impact": plot_impact,
            "power_score": power_score,
            "mental_score": mental_score,
            "radar": {
                "叙事掌控度": plot_impact,
                "战力与危险度": power_score,
                "谋略与心智": mental_score,
                "社会身份复制度": round(alias_points * 5.0, 1),
                "心理韧性": round(min(recovery_points * 6.0 + 30.0, 100.0), 1),
            },
        }
