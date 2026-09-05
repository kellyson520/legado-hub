from __future__ import annotations

import itertools
import re
from collections import Counter
from typing import Any


class CharacterCalibrationService:
    def __init__(self, ai_service=None):
        self._ai_service = ai_service

    async def calibrate(
        self,
        keyword: str,
        items: list[dict[str, Any]],
        actor_id: str = "system",
    ) -> dict[str, Any]:
        enriched_items = []
        for item in items:
            characters = self._extract_characters(item.get("excerpt", ""))
            enriched_items.append({**item, "characters": characters})

        pairwise = []
        for left, right in itertools.combinations(enriched_items, 2):
            left_set = set(left["characters"])
            right_set = set(right["characters"])
            overlap = self._jaccard(left_set, right_set)
            pairwise.append(
                {
                    "left_source_id": left.get("source_id"),
                    "right_source_id": right.get("source_id"),
                    "overlap_score": overlap,
                    "shared_characters": sorted(left_set & right_set),
                }
            )

        provider_result = None
        if self._ai_service is not None:
            try:
                joined = "\n\n".join(
                    [
                        f"[source_id={item.get('source_id')}] {item.get('name', '')} / {item.get('author', '')}\n"
                        f"{item.get('excerpt', '')}"
                        for item in items
                    ]
                )
                provider_result = await self._ai_service.run_character_analysis(
                    {"title": keyword, "content": joined},
                    actor_id=actor_id,
                )
            except Exception:
                provider_result = None

        return {
            "keyword": keyword,
            "items": enriched_items,
            "pairwise": pairwise,
            "used_provider": provider_result is not None,
            "provider_result": provider_result,
        }

    @staticmethod
    def _extract_characters(text: str, top_k: int = 5) -> list[str]:
        text = text or ""
        compact = re.sub(r"[^\u4e00-\u9fff]", "", text)
        tokens: list[str] = []
        for size in (2, 3):
            for index in range(0, max(len(compact) - size + 1, 0)):
                tokens.append(compact[index : index + size])
        stopwords = {
            "第一章",
            "第二章",
            "第三章",
            "第四章",
            "第五章",
            "众人",
            "尸体",
            "河边",
            "学院",
            "修炼",
        }
        invalid_chars = {"的", "了", "和", "在", "与", "来", "到", "看", "见", "发", "现", "决", "定", "负", "责"}
        counter = Counter(
            token
            for token in tokens
            if token not in stopwords
            and not any(char in invalid_chars for char in token)
        )
        return [name for name, _ in counter.most_common(top_k)]

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)
